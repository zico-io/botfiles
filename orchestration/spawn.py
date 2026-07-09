#!/usr/bin/env python3
"""spawn.py — stand up / tear down a 3-layer agent fleet on herdr.

Reads a roster JSON, spawns leads (layer 2) as herdr tabs and workers (layer 3)
as pane splits inside their lead's tab, launches each harness binary, waits for
it to be ready, then injects a bootstrap prompt that joins the agent's orbal-net room.

herdr owns placement/process/status; the per-mission orbal-net server (`orbal-net serve`,
started here on the host - see orbal_net_up) owns coordination - agents reach it with
the same `orbal-net` CLI over TCP. The orchestrator is layer 1 — the pane you are already
in — and is NOT spawned here.

Usage:
  python3 spawn.py up   <roster.json> [teams]  # spawns fleet, prints {role: pane_id} JSON
                                               # teams = comma list of lead roles; omit = whole roster
  python3 spawn.py poke <feature> <role> [msg] # wake an idle agent (orbal-net nudges don't auto-submit)
  python3 spawn.py status <feature>            # mission health: server, container, agents, rooms
  python3 spawn.py bridge-pr <feature> [title] # push mission-<feature> to origin + open a PR via gh
  python3 spawn.py down <feature>              # tears down squad rooms + closes the workspace
  python3 spawn.py selfcheck                   # asserts the layer/hierarchy rules

See orchestration/roster.example.json and .claude/commands/spawn-team.md.
"""
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

# The `eve` harness pane runs the built eve production server (`eve start`, :3000),
# NOT an agent TUI. It: wipes the durable store (parked sessions from a prior run
# resume and refire tool calls, stalling startup); installs deps - a fresh mission
# clone has NO node_modules (gitignored), so `eve build`/`start` cannot boot without
# this (`npm ci` from the committed lockfile, falling back to `npm install`); links a
# Vercel project so the model resolves via AI Gateway (writes .env.local with a fresh
# VERCEL_OIDC_TOKEN; the TEAM slug is `zico-ios-projects` - the personal handle
# `zico-io` is rejected as a scope); then serves. `-w /work` (from sandbox_wrap) is
# the cwd. Parens (not braces) group the install so this stays safe under .format().
# No {model} is used (agent.ts pins it); {role}/{model} pass through .format harmlessly.
EVE_START_CMD = (
    "sh -lc 'rm -rf .workflow-data && "
    "(npm ci || npm install) && "
    "npx eve build && "
    "vercel link --yes --scope zico-ios-projects --project bob >/dev/null 2>&1; "
    "exec npx eve start'"
)

# Per-harness launch template + a startup substring herdr waits for before we
# inject the bootstrap prompt. {model}/{role} are filled per role.
# ponytail: ready strings and flags are version-sensitive — tune here if a
# harness changes its startup banner or the `--model` flag.
HARNESSES = {
    "claude": {"cmd": "claude --dangerously-skip-permissions --model {model}", "ready": "bypass permissions on", "working": "esc to interrupt"},
    "codex":  {"cmd": "codex --dangerously-bypass-approvals-and-sandbox --model {model}", "ready": "Codex", "working": "esc to interrupt"},
    "pi":     {"cmd": "pi --name {role} --model {model}", "ready": "pi", "working": "esc to interrupt"},
    # eve is a server pane, not a TUI: ready when it logs it is serving on :3000;
    # it has no "working" marker (turns are sub-second Function calls on the session
    # stream, not a busy footer), so launch() skips bootstrap()/submit for it.
    "eve":    {"cmd": EVE_START_CMD, "ready": "server listening at http://127.0.0.1:3000/", "working": None},
}

READY_TIMEOUT_MS = "90000"  # ponytail: cold microVM start; raise if the VM/host gets slower
# The eve pane runs `npm ci` + `npx eve build` before `eve start` serves (a fresh
# mission clone has no node_modules/.output, both gitignored), which can exceed the
# generic ready timeout. Give the eve pane its own longer ceiling. ponytail: raise
# if a cold `npm ci` + `eve build` gets slower.
EVE_READY_TIMEOUT_MS = os.environ.get("EVE_READY_TIMEOUT_MS", "180000")
SUBMIT_TIMEOUT_MS = "15000"  # how long to wait for an injected prompt to start running

# Sandbox: run each mission inside one Apple `container` microVM (per-mission
# granularity). Agents attach as `container exec` processes, so herdr's PTY
# (banner match + send-keys) works unchanged; coordination is the host orbal-net
# server reached over TCP with the `orbal-net` CLI (ORBAL_NET_* env injected per exec).
# Default ON; BOTFILE_NO_SANDBOX=1 runs bare on the host (debugging only).
# See .botfile/memory/tools/sandbox.md and sandbox/build.sh.
SANDBOX = os.environ.get("BOTFILE_NO_SANDBOX") != "1"
CONTAINER_IMAGE = "botfiles-agent"
# Per-mission VM resources. Apple `container` defaults to 4 CPU / 1 GB, which is
# too little to run a Rust toolchain across several agents (cargo OOMs/thrashes).
# Override per mission with MISSION_CPUS / MISSION_MEMORY.
CONTAINER_CPUS = os.environ.get("MISSION_CPUS", "8")
CONTAINER_MEMORY = os.environ.get("MISSION_MEMORY", "12g")
SECRETS_ROOT = "/tmp/botfile-secrets"
MISSIONS_ROOT = "/tmp/botfile-missions"  # per-mission clone + state, keyed by feature


def container(*args, check=True, timeout=None):
    """Run an Apple `container` CLI command; return stdout stripped."""
    return subprocess.run(["container", *args], capture_output=True, text=True,
                          check=check, timeout=timeout).stdout.strip()


def _force_kill_container(name):
    """SIGKILL the per-mission runtime process for a wedged VM (its uuid == name).
    A thrashed guest can hang the Apple `container` daemon so `rm`/`stop` block
    forever; killing container-runtime-linux directly lets the daemon reap it."""
    out = subprocess.run(["pgrep", "-f", f"container-runtime-linux.*--uuid {name}"],
                         capture_output=True, text=True).stdout.split()
    for pid in out:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ProcessLookupError, ValueError):
            pass


def mission_workdir(feature, repo):
    """The host dir to mount at /work — isolated per mission so parallel missions
    on one repo don't clobber each other.

    A bare `git worktree` can't be bind-mounted alone: its `.git` points into the
    main repo's `.git`, which is outside the mount, so git breaks in the guest.
    Instead each mission gets a self-contained local clone (hardlinked objects, so
    it's cheap) on branch `mission-<feature>`; commits land there and are fetched
    back into `repo` on teardown. A non-git `repo` falls back to a direct shared
    mount (today's behavior). Only committed state is cloned.
    """
    if subprocess.run(["git", "-C", repo, "rev-parse", "--git-dir"], capture_output=True).returncode != 0:
        print(f"warning: {repo} is not a git repo — missions share its files", file=sys.stderr)
        return repo
    work = os.path.join(MISSIONS_ROOT, feature, "work")
    if not os.path.isdir(os.path.join(work, ".git")):
        os.makedirs(os.path.dirname(work), exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", repo, work], check=True)
    subprocess.run(["git", "-C", work, "checkout", "-B", f"mission-{feature}"],
                   check=True, capture_output=True)
    # A fresh clone carries no author identity inside the mission VM (the host's
    # global git config isn't mounted there), so an agent's first commit dies with
    # "Author identity unknown". Seed the clone's local config from the host
    # identity, per-key, falling back to a default when the host hasn't set it.
    for key, default in (("user.name", "gilbert"), ("user.email", "gilbert@botfiles.local")):
        host = subprocess.run(["git", "-C", repo, "config", key],
                              capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", work, "config", key, host or default], check=True)
    return work


def _state_path(feature):
    return os.path.join(MISSIONS_ROOT, feature, "mission.json")


def _load_state(feature):
    try:
        return json.load(open(_state_path(feature)))
    except FileNotFoundError:
        return {}


def _save_state(feature, **kw):
    """Merge keys into the per-mission state file (created if missing)."""
    p = _state_path(feature)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    st = _load_state(feature)
    st.update(kw)
    json.dump(st, open(p, "w"))


def harvest(feature, repo, workdir):
    """Fetch the mission's branch back into the origin repo so its commits survive
    the clone being deleted. Returns True on success. (Agents can't push from
    inside the VM — origin isn't mounted there — so this runs on the host.)"""
    branch = f"mission-{feature}"
    r = subprocess.run(["git", "-C", repo, "fetch", workdir, f"+{branch}:{branch}"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print(f"harvested {branch} into {repo}")
        return True
    # git refuses to update a branch that is checked out in a worktree. Preserve the
    # commits under a side ref so the clone is still safe to delete; the branch itself
    # keeps whatever it had (usually already up to date - that's why it was checked out).
    backup = f"refs/botfile-harvest/{feature}"
    r2 = subprocess.run(["git", "-C", repo, "fetch", workdir, f"+{branch}:{backup}"],
                        capture_output=True, text=True)
    if r2.returncode == 0:
        print(f"harvested {branch} -> {backup} ({branch} busy: {r.stderr.strip()})")
        return True
    print(f"warning: could not harvest {branch}: {r.stderr.strip()}", file=sys.stderr)
    return False


def _pr_cmd(branch, title):
    """Build the `gh pr create` argv. Pure (selfcheck-testable): with a title we set an
    explicit body, otherwise `--fill` pulls title+body from the branch's commits."""
    cmd = ["gh", "pr", "create", "--head", branch, "--base", "main"]
    return cmd + (["--title", title, "--body", f"Bridged mission branch `{branch}`."]
                  if title else ["--fill"])


def bridge_pr(feature, title=None):
    """Push the mission branch to the origin remote and open a PR via `gh`.

    Agents have no gh/network and their clone's origin is a local mirror, so the
    orchestrator ships their work: harvest the branch into the origin repo (whose origin
    IS the real remote), push it, then open the PR from the host. Reuses `harvest`.
    """
    st = _load_state(feature)
    repo, workdir = st.get("repo"), st.get("workdir")
    if not repo:
        sys.exit(f"no mission state for {feature!r} (run `up` first)")
    branch = f"mission-{feature}"
    if workdir and not harvest(feature, repo, workdir):
        sys.exit(f"could not harvest {branch} into {repo}; resolve before bridging")
    if subprocess.run(["git", "-C", repo, "push", "-u", "origin", branch]).returncode != 0:
        sys.exit(f"git push of {branch} to origin failed")
    if subprocess.run(_pr_cmd(branch, title), cwd=repo).returncode != 0:
        sys.exit("gh pr create failed (already open? see `gh pr list`)")


def mission_secrets(feature):
    """Write harness credentials to a per-mission dir mounted read-only into the VM.

    claude keeps its OAuth cred in the macOS Keychain (no file); export it to a
    .credentials.json the Linux guest reads. codex already keeps an auth file.
    The secret goes straight to disk and into the guest, never to stdout — the
    sandbox necessarily gets a copy so agents can call the model APIs (same trust
    as running the harness on the host). Absent creds are skipped, not faked.
    """
    d = os.path.join(SECRETS_ROOT, feature)
    os.makedirs(d, mode=0o700, exist_ok=True)
    cred = os.path.join(d, "claude.credentials.json")
    with open(cred, "wb") as f:
        rc = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                            stdout=f, stderr=subprocess.DEVNULL).returncode
    if rc != 0 or os.path.getsize(cred) == 0:
        os.remove(cred)
    codex = os.path.expanduser("~/.codex/auth.json")
    if os.path.exists(codex):
        shutil.copyfile(codex, os.path.join(d, "codex.auth.json"))
    # Vercel CLI cred (host `vercel login`), so in-VM agents can `vercel deploy`.
    vercel = os.path.expanduser("~/Library/Application Support/com.vercel.cli/auth.json")
    if os.path.exists(vercel):
        shutil.copyfile(vercel, os.path.join(d, "vercel.auth.json"))
    return d


# Pre-answers claude's first-run prompts inside the mission VM (see mission_up).
CLAUDE_SEED = (
    "import json,os\n"
    "cj='/root/.claude.json'\n"
    "d=json.load(open(cj)) if os.path.exists(cj) else {}\n"
    "d['hasCompletedOnboarding']=True\n"
    "d.setdefault('theme','dark')\n"
    "d.setdefault('projects',{}).setdefault('/work',{})['hasTrustDialogAccepted']=True\n"
    "json.dump(d,open(cj,'w'))\n"
    "sj='/root/.claude/settings.json'\n"
    "s=json.load(open(sj)) if os.path.exists(sj) else {}\n"
    "s['skipDangerousModePermissionPrompt']=True\n"
    "os.makedirs('/root/.claude',exist_ok=True)\n"
    "json.dump(s,open(sj,'w'))\n"
)

# codex's counterpart: --dangerously-bypass-approvals-and-sandbox does NOT skip
# the /work folder-trust prompt, so a fresh codex hangs on it. Persist the same
# trust codex would write on "Yes" so its TUI boots straight to ready.
# Idempotent; harmless for claude-only missions.
CODEX_SEED = (
    "import os\n"
    "p='/root/.codex/config.toml'\n"
    "os.makedirs('/root/.codex',exist_ok=True)\n"
    "s=open(p).read() if os.path.exists(p) else ''\n"
    "if 'projects.\"/work\"' not in s:\n"
    "    open(p,'w').write(s+'\\n[projects.\"/work\"]\\ntrust_level = \"trusted\"\\n')\n"
)


def mission_up(feature, repo):
    """Start the per-mission microVM: isolated clone at /work, creds at /secrets."""
    name = f"mission-{feature}"
    container("rm", "-f", name, check=False)  # clear any stale container
    workdir = mission_workdir(feature, repo)
    secrets = mission_secrets(feature)
    container("run", "-d", "--name", name,
              "-c", CONTAINER_CPUS, "-m", CONTAINER_MEMORY,
              "-v", f"{workdir}:/work", "-v", f"{secrets}:/secrets:ro", "-w", "/work",
              CONTAINER_IMAGE, "sleep", "infinity")
    # The image ships credentials but a fresh claude still blocks on three
    # first-run prompts that --dangerously-skip-permissions does NOT skip:
    # the theme picker, the /work folder-trust dialog, and the bypass-mode
    # acceptance. Pre-answer all three so the TUI boots straight to ready.
    # Idempotent; harmless for codex-only missions.
    container("exec", name, "python3", "-c", CLAUDE_SEED)
    container("exec", name, "python3", "-c", CODEX_SEED)
    os.makedirs(os.path.dirname(_state_path(feature)), exist_ok=True)
    json.dump({"repo": repo, "workdir": workdir}, open(_state_path(feature), "w"))
    return name


def mission_down(feature):
    name = f"mission-{feature}"
    try:
        container("rm", "-f", name, check=False, timeout=30)
    except subprocess.TimeoutExpired:
        print(f"`container rm {name}` hung; force-killing its runtime", file=sys.stderr)
        _force_kill_container(name)
    shutil.rmtree(os.path.join(SECRETS_ROOT, feature), ignore_errors=True)
    try:
        state = json.load(open(_state_path(feature)))
    except FileNotFoundError:
        shutil.rmtree(os.path.join(MISSIONS_ROOT, feature), ignore_errors=True)
        return
    # Harvest the mission branch before deleting the clone; keep it if harvest
    # fails so no committed work is lost. (Direct-mount fallback has no clone.)
    kept = state["workdir"] != state["repo"] and not harvest(feature, state["repo"], state["workdir"])
    if kept:
        print(f"kept mission clone at {state['workdir']} (harvest failed; work preserved)", file=sys.stderr)
    else:
        shutil.rmtree(os.path.join(MISSIONS_ROOT, feature), ignore_errors=True)


def sandbox_wrap(cmd, feature, env=None):
    """Wrap a harness command so it runs inside the mission's microVM, carrying
    `env` (the ORBAL_NET_* identity/coords) into the agent's shell.

    With env=None the output is byte-identical to the un-wrapped form, so the
    hierarchy self-check stays valid. Bare mode prefixes the vars instead of
    passing `-e` flags. (ORBAL_NET_* values contain no spaces, so no quoting needed.)
    """
    if SANDBOX:
        flags = "".join(f"-e {k}={v} " for k, v in (env or {}).items())
        return f"container exec -it {flags}-w /work mission-{feature} {cmd}"
    prefix = "".join(f"{k}={v} " for k, v in (env or {}).items())
    return f"{prefix}{cmd}"


def _advertise_host():
    """Primary IP that guests/remote containers can reach the host on (not loopback).

    Uses the UDP-connect trick (no packet is sent) to pick the egress interface's
    address; override with ORBAL_NET_ADVERTISE_HOST for VPN/remote topologies.
    """
    override = os.environ.get("ORBAL_NET_ADVERTISE_HOST")
    if override:
        return override
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _pid_alive(pid):
    """True if `pid` is a live process (owned by us or anyone)."""
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, ValueError):
        return True  # exists but not ours (still alive)


def _read_port(log_path, proc, deadline=10):
    """Wait for the server's `{"port": N}` first log line; fail loud on early exit."""
    end = time.time() + deadline
    while time.time() < end:
        if proc.poll() is not None:
            sys.exit(f"orbal-net server exited early (rc={proc.returncode}); see {log_path}")
        first = ""
        try:
            with open(log_path) as f:
                first = f.readline().strip()
        except FileNotFoundError:
            pass
        if first:
            try:
                return json.loads(first)["port"]
            except (json.JSONDecodeError, KeyError):
                proc.kill()
                sys.exit(f"orbal-net server first line was not a port: {first!r} (see {log_path})")
        time.sleep(0.05)
    proc.kill()
    sys.exit(f"orbal-net server never reported a port within {deadline}s (see {log_path})")


def _ensure_orbal_net():
    """Make sure the `orbal-net` binary is on PATH, installing it if not.

    Tries the crates.io release first; until v0.1.0 is published (or if the
    registry copy is unreachable) falls back to installing straight from the
    public repo so a fresh host can still stand up a mission.
    """
    if shutil.which("orbal-net"):
        return
    print("orbal-net not on PATH; installing...", file=sys.stderr)
    if subprocess.run(["cargo", "install", "orbal-net"]).returncode == 0:
        return
    r = subprocess.run(["cargo", "install", "--git", "https://github.com/zico-io/orbal-net", "orbal-net"])
    if r.returncode != 0:
        sys.exit("could not install orbal-net (tried crates.io and git); install manually")


def orbal_net_up(feature):
    """Start this mission's authoritative orbal-net server (`orbal-net serve`) on the host and
    record how to reach it in mission.json. One server per mission; killing it at
    teardown is the room cleanup. State persists to orbal-net.db beside mission.json, so a
    server restart mid-mission keeps every room and message. Runs in every mode (the
    server is a host process, VM or not)."""
    _ensure_orbal_net()
    token = secrets.token_hex(16)
    state_dir = os.path.join(MISSIONS_ROOT, feature)
    os.makedirs(state_dir, exist_ok=True)
    db = os.path.join(state_dir, "orbal-net.db")
    log_path = os.path.join(state_dir, "orbal-net.log")
    log = open(log_path, "w")
    try:
        # start_new_session detaches the server from spawn.py's process group so a
        # Ctrl-C / pane close in the launching terminal can't take it down mid-mission.
        # Output goes to orbal-net.log (not a pipe) so it can never block on a full buffer
        # and leaves a trace if the server dies.
        proc = subprocess.Popen(["orbal-net", "serve", "--token", token, "--db", db],
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    except FileNotFoundError:
        sys.exit("orbal-net server failed to start: `orbal-net` binary not on PATH "
                 "(cargo's bin dir may be missing from PATH; see _ensure_orbal_net)")
    port = _read_port(log_path, proc)
    url = f"http://{_advertise_host()}:{port}"
    _save_state(feature, orbal_net_url=url, orbal_net_token=token, orbal_net_pid=proc.pid)
    return url


# --- eve connector lifecycle (symmetric to orbal_net_up) ---------------------
# A LOCAL eve role runs `eve start` in a herdr pane inside the mission VM; its
# connector runs ALONGSIDE it (same VM in sandbox mode; same host in bare mode),
# because the connector must reach BOTH the eve server (127.0.0.1:3000, in the VM)
# and orbal-net (the host LAN url, reachable from the VM's open egress). The
# connector owns its pidfile/log/cursor under the mission clone (/work in the VM =
# the workdir on the host via the bind mount), so host-side status()/down() read
# them through the mount. This is the one genuinely new always-on dependency this
# harness adds (RFC S10 risk 2); a dead connector is silent, so status() surfaces
# it. Files live under /work; bob's .gitignore excludes `.bob-connector.*`.

# In-VM (== /work) paths; on the host these are under st["workdir"].
_BOB_CONNECTOR_PID = ".bob-connector.pid"
_BOB_CONNECTOR_LOG = ".bob-connector.log"
_BOB_CONNECTOR_CURSOR = ".bob-connector-cursor.json"


def _connector_host_paths(st):
    """Host-visible paths for the connector's pidfile + log (via the /work mount).
    Bare mode has no VM, so the workdir IS the host path either way."""
    wd = st["workdir"]
    return os.path.join(wd, _BOB_CONNECTOR_PID), os.path.join(wd, _BOB_CONNECTOR_LOG)


def orbal_net_connector_up(feature, agent, room):
    """Start the standalone orbal-net -> eve connector for the eve leaf role.

    Detached, alongside `eve start`. The connector writes its own pidfile (the
    authoritative pid record) + heartbeat log under /work; we record the agent,
    room, and those paths in mission.json. Called by up() after the eve pane is
    READY (so EVE_URL :3000 answers; a connector that starts first just retries).
    """
    st = _load_state(feature)
    env = {
        "ORBAL_NET_URL": st["orbal_net_url"],
        "ORBAL_NET_TOKEN": st["orbal_net_token"],
        "ORBAL_NET_AGENT": agent,
        "ORBAL_NET_ROOM": room,
        "EVE_URL": "http://127.0.0.1:3000",
        "CONNECTOR_PID_PATH": f"/work/{_BOB_CONNECTOR_PID}" if SANDBOX else os.path.join(st["workdir"], _BOB_CONNECTOR_PID),
        "CONNECTOR_LOG_PATH": f"/work/{_BOB_CONNECTOR_LOG}" if SANDBOX else os.path.join(st["workdir"], _BOB_CONNECTOR_LOG),
        "CONNECTOR_CURSOR_PATH": f"/work/{_BOB_CONNECTOR_CURSOR}" if SANDBOX else os.path.join(st["workdir"], _BOB_CONNECTOR_CURSOR),
    }
    if SANDBOX:
        # Detach inside the VM: nohup + background so `container exec` returns while
        # node keeps running as a child of the VM's init. The connector's own
        # console output goes to .bob-connector.stdout (crash diagnostics); its
        # heartbeat log (mtime source for status) is CONNECTOR_LOG_PATH, which it
        # appends to itself. ponytail: if `container exec` detach ever reaps the
        # child on return, switch to a host Popen of `container exec ... node ...`.
        # nohup + `&` alone survives the exec shell exiting (the container `sh` is
        # dash/busybox, which has no `disown` builtin - it would exit 127). nohup
        # guards SIGHUP; node reparents to the VM's init when this shell returns.
        envs = "".join(f"{k}={v} " for k, v in env.items())
        inner = f"nohup env {envs}node /work/connector/main.ts >>/work/.bob-connector.stdout 2>&1 &"
        subprocess.run(["container", "exec", f"mission-{feature}", "sh", "-lc", inner], check=True)
    else:
        log = open(os.path.join(MISSIONS_ROOT, feature, "bob-connector.stdout"), "a")
        subprocess.Popen(["node", os.path.join(st["workdir"], "connector", "main.ts")],
                         env={**os.environ, **env}, cwd=st["workdir"],
                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    _save_state(feature, eve_connector={"agent": agent, "room": room})
    return env


def _connector_invm_pid(st):
    """Read the connector's own pidfile (in-VM pid), via the host /work mount."""
    pidfile, _ = _connector_host_paths(st)
    try:
        return int(open(pidfile).read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _vm_kill(feature, sig, pid):
    """Signal an in-VM pid. `kill` is a shell BUILTIN, not a standalone executable in
    the mission image, so `container exec ... kill` fails ("target executable kill");
    it must run through a shell. Returns the CompletedProcess (returncode 0 = signal
    delivered / process exists for -0)."""
    return subprocess.run(["container", "exec", f"mission-{feature}", "sh", "-lc", f"kill -{sig} {pid}"],
                          capture_output=True)


def orbal_net_connector_down(feature):
    """Gracefully stop the connector (SIGTERM -> grace -> SIGKILL) so it fsyncs its
    cursor before exit. In sandbox mode the following `container rm -f` (mission_down)
    is the hard backstop that reaps it with the VM regardless; this just gives it a
    clean shutdown first. No-op if there is no eve connector for this mission."""
    st = _load_state(feature)
    if not st.get("eve_connector"):
        return
    pid = _connector_invm_pid(st)
    if not pid:
        return
    if SANDBOX:
        # Signal the in-VM pid through the VM (host os.kill can't reach a VM pid).
        _vm_kill(feature, "TERM", pid)
        for _ in range(50):  # up to ~5s grace for a clean cursor-flushing exit
            if _vm_kill(feature, "0", pid).returncode != 0:
                break
            time.sleep(0.1)
        else:
            _vm_kill(feature, "9", pid)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(50):
                if not _pid_alive(pid):
                    break
                time.sleep(0.1)
            else:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def orbal_net_connector_status(feature, st):
    """One status line for the connector: pid liveness + heartbeat freshness.
    A stale heartbeat with a live pid is the important STALLED case (wedged, not
    exited). Mirrors how status() reports the orbal-net server."""
    ec = st.get("eve_connector")
    if not ec:
        return None
    pid = _connector_invm_pid(st)
    if not pid:
        return f"  eve connector ({ec['agent']} in {ec['room']}): DOWN (no pidfile)"
    if SANDBOX:
        alive = _vm_kill(feature, "0", pid).returncode == 0
    else:
        alive = _pid_alive(pid)
    _, logfile = _connector_host_paths(st)
    try:
        fresh = (time.time() - os.path.getmtime(logfile)) < 30  # heartbeat every ~10s
    except FileNotFoundError:
        fresh = False
    state = "UP" if (alive and fresh) else ("STALLED (pid alive, heartbeat stale)" if alive else "DOWN")
    return f"  eve connector ({ec['agent']} in {ec['room']}): {state}  pid {pid}"


def _verify_agent_orbal_net(feature):
    """Fail loud if the agent environment can't resolve `orbal-net` before launch.

    Agents reach the mission server through this binary; if it is missing they fall back
    to recompiling it from the mission repo at join - slow, and it trips the repo's pinned
    toolchain. In SANDBOX the binary is baked into the image, so a stale/broken image (e.g.
    a swallowed install in provision.sh, or a pre-rebrand image with only `comms`) must
    abort `up` here rather than degrade silently. Bare mode shares the host PATH, already
    guaranteed by `_ensure_orbal_net`.
    """
    if SANDBOX:
        r = subprocess.run(["container", "exec", f"mission-{feature}", "sh", "-lc",
                            "command -v orbal-net"], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"mission image lacks orbal-net on PATH - rebuild the sandbox image so "
                     f"provision.sh reinstalls it; the comms->orbal-net rebrand likely left a "
                     f"stale image. (checked: container exec mission-{feature} command -v orbal-net)")
    elif not shutil.which("orbal-net"):
        sys.exit("orbal-net not on PATH for agents (bare mode) - install it before spawning "
                 "(`cargo install orbal-net`)")


def orbal_net_post(feature, agent, action, **fields):
    """POST one orbal-net action to this mission's server as `agent` (host-side, no CLI).

    Lets `up` seed rooms before any agent boots - notably create the mission room
    as the orchestrator so it owns+joins it and can `orbal-net send` immediately
    (op_join 404s on a missing room, so someone must create it first).
    """
    st = _load_state(feature)
    req = urllib.request.Request(
        f"{st['orbal_net_url'].rstrip('/')}/{action}",
        data=json.dumps({"agent": agent, **fields}).encode(),
        headers={"Authorization": f"Bearer {st['orbal_net_token']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def herdr(*args):
    """Run a herdr command; return parsed JSON. Raise on socket/API errors."""
    out = subprocess.run(["herdr", *args], capture_output=True, text=True, check=True).stdout.strip()
    if not out:
        return None
    try:
        doc = json.loads(out)
    except json.JSONDecodeError:
        return out  # `pane read` returns plain text
    if isinstance(doc, dict) and doc.get("error"):
        raise RuntimeError(f"herdr {' '.join(args)}: {doc['error'].get('message', doc['error'])}")
    return doc


def validate(roster):
    """Enforce the hierarchy: <=3 layers, single orchestrator root, leaf workers.

    Layer 1 = orchestrator (implicit; the parent of every lead). Leads are
    layer 2 (parent == "orchestrator"). Anything deeper is a worker; a worker
    (layer 3) may not itself be a parent, and layer 4+ is rejected.
    """
    roles = {r["role"]: r for r in roster["roles"]}
    if not roles:
        raise ValueError("roster has no roles")
    parents = {r["parent"] for r in roster["roles"]}

    def layer(role, seen=()):
        if role in seen:
            raise ValueError(f"cycle in parent chain at {role!r}")
        p = roles[role]["parent"]
        if p == "orchestrator":
            return 2
        if p not in roles:
            raise ValueError(f"{role}: unknown parent {p!r}")
        return layer(p, seen + (role,)) + 1

    for role in roles:
        depth = layer(role)
        if depth > 3:
            raise ValueError(f"{role}: layer {depth} exceeds the 3-layer max")
        if depth == 3 and role in parents:
            raise ValueError(f"{role}: layer-3 worker cannot be a parent")
    return roles


def bootstrap(role, harness, feature, parent, has_brief=False):
    """First-turn prompt: join the right orbal-net room via the `orbal-net` CLI.

    Identity is preset in $ORBAL_NET_AGENT (injected per exec), so the server upserts
    the agent on its first call - no explicit register step.
    """
    mission = f"mission-{feature}"
    if parent == "orchestrator":  # lead (layer 2)
        squad = f"squad-{role}"
        # The brief is posted to the mission room by `up` before leads join, so pull it
        # with `read --since 0` (full history) and relay it into the squad for workers.
        brief = (
            f"After joining, run `orbal-net read {mission} --since 0` to pull the mission brief "
            f"(posted before you joined) - it is your guiding scope; then relay it to your "
            f"workers with `orbal-net send {squad} <brief>`. "
        ) if has_brief else ""
        return (
            f"You are '{role}', a {harness} agent in mission '{feature}', parent orchestrator. "
            f"Your orbal-net identity is preset in $ORBAL_NET_AGENT. The `orbal-net` CLI is "
            f"preinstalled on PATH; if it is ever not found, STOP and report it - do NOT build it "
            f"from the mission repo. Run these shell commands now: "
            f"`orbal-net join {mission}`, `orbal-net create-room {squad}`, `orbal-net send {mission} ready`. "
            + brief +
            f"Then await tasks by BLOCKING on `orbal-net recv {mission}` — it returns the moment a "
            f"message arrives, so NEVER write a shell poll loop (no `while`/`for`/`sleep` around "
            f"orbal-net). For each task: delegate to your workers in '{squad}' with `orbal-net send {squad} "
            f"<task>`, collect their results (block on `orbal-net recv {squad}`), report up to "
            f"'{mission}' with `orbal-net send {mission} <result>`, then loop back to `orbal-net recv "
            f"{mission}`. Emit progress events so an observer can follow the fleet in `orbal-net tui`: "
            f"`orbal-net event {mission} task-start --task '<label>'` on a new task, `orbal-net event "
            f"{mission} phase --phase '<what the squad is doing>'` while delegating, and `orbal-net "
            f"event {mission} task-done --task '<label>'` when you report the result up. "
            f"Run `orbal-net status done` when finished. Never spawn agents below layer 3."
        )
    squad = f"squad-{parent}"  # worker (layer 3)
    return (
        f"You are '{role}', a {harness} agent, parent '{parent}'. Your orbal-net identity is preset "
        f"in $ORBAL_NET_AGENT. The `orbal-net` CLI is preinstalled on PATH; if it is ever not found, "
        f"STOP and report it - do NOT build it from the mission repo. "
        f"Run `orbal-net join {squad}` then `orbal-net send {squad} ready`. Then BLOCK on "
        f"`orbal-net recv {squad}` for each task — it returns as soon as a message arrives, so NEVER "
        f"write a shell poll loop (no `while`/`for`/`sleep` around orbal-net). Do the task, and "
        f"whenever it changes files commit them with `wcommit '{role}: <what changed>' <the files "
        f"you changed>` before you report - you share one clone with other workers, so wcommit "
        f"serializes the commit and stages only your files (never `git add -A`); only committed "
        f"work is harvested back to the repo at teardown. As you work, emit progress so an "
        f"observer can follow you in `orbal-net tui`: `orbal-net event {squad} task-start --task '<short "
        f"label>'` when you start, `orbal-net progress {squad} <done>/<total>` or `orbal-net event {squad} "
        f"phase --phase '<current step>'` at milestones, `orbal-net event {squad} blocked --to "
        f"<who-or-what>` if you stall, and `orbal-net event {squad} task-done --task '<label>'` before "
        f"you report. Report results with `orbal-net send {squad} <result>`, loop back to `orbal-net recv "
        f"{squad}`, and run `orbal-net status done` when finished. You are a leaf — do not spawn agents."
    )


def submit(pane, spec):
    r"""Confirm an injected prompt actually started running; resend the submit key if not.

    A freshly-split or just-woken pane can swallow the submit key, leaving the prompt
    typed but unsent. NOTE: Claude's TUI ignores a bare `send-keys Enter`, and a `\n`
    (line feed) only submits short inputs; the reliable submit is a carriage return
    (`\r`) - the actual Enter key. Sending it to an already-running (empty) prompt is a
    harmless no-op, so this is safe to always run.
    """
    try:
        herdr("wait", "output", pane, "--match", spec["working"], "--timeout", SUBMIT_TIMEOUT_MS)
    except subprocess.CalledProcessError:
        herdr("pane", "send-text", pane, "\r")
        try:
            herdr("wait", "output", pane, "--match", spec["working"], "--timeout", SUBMIT_TIMEOUT_MS)
        except subprocess.CalledProcessError:
            # Prompt was almost certainly already submitted: the agent is off running a
            # foreground command (e.g. an `orbal-net` poll loop), whose TUI footer isn't the
            # idle "working" marker we wait for. Best-effort confirm, so don't abort the
            # whole fleet over it. ponytail: if a pane truly swallowed the prompt, poke it.
            pass


def launch(pane, role, harness, model, feature, parent, has_brief=False):
    """Run the harness in `pane`, wait for it to be ready, inject the bootstrap.

    Each agent's shell carries its orbal-net coordinates + identity so the baked-in
    `orbal-net` CLI (and its subshells) can reach the mission server as this role.
    """
    spec = HARNESSES[harness]
    st = _load_state(feature)
    env = {"ORBAL_NET_URL": st["orbal_net_url"], "ORBAL_NET_TOKEN": st["orbal_net_token"], "ORBAL_NET_AGENT": role}
    if harness == "eve":
        # An eve role's pane runs the durable server (`eve start`), not an agent
        # TUI. The join/recv/emit protocol is compiled into the eve project's
        # channel + tools, so there is NO bootstrap()/submit step. The room is
        # injected so the outbound tools default to the right room; the connector
        # (orbal_net_connector_up) feeds this server its inbound frames. Waits on a
        # longer ceiling because the pane runs npm ci + eve build before eve start.
        env["ORBAL_NET_ROOM"] = f"squad-{parent}"
        herdr("pane", "run", pane, sandbox_wrap(spec["cmd"].format(model=model, role=role), feature, env))
        herdr("wait", "output", pane, "--match", spec["ready"], "--timeout", EVE_READY_TIMEOUT_MS)
        return
    herdr("pane", "run", pane, sandbox_wrap(spec["cmd"].format(model=model, role=role), feature, env))
    herdr("wait", "output", pane, "--match", spec["ready"], "--timeout", READY_TIMEOUT_MS)
    herdr("pane", "run", pane, bootstrap(role, harness, feature, parent, has_brief))
    submit(pane, spec)


def poke(feature, role, message=None):
    """Wake an agent by submitting a prompt straight into its pane.

    `orbal-net recv` gives push while an agent is blocked on it, but an agent sitting idle
    at its prompt (between tasks, or not currently waiting) won't see a new room message
    on its own. `herdr pane run` types AND submits a prompt, which wakes the agent so it
    re-checks orbal-net. This is a herdr/PTY-level nudge, not an orbal-net message, so it
    does not put the orchestrator into a worker's room - the hierarchy holds. In sandbox
    mode only the host can reach herdr, so pokes originate from the orchestrator. Use
    whenever a target didn't act on a room message. (herdr is host-pane-local, so this
    can only wake local-VM agents - see the remote-wake gap in orchestration.md.)
    """
    st = _load_state(feature)
    info = (st.get("roles") or {}).get(role)
    if not info:
        sys.exit(f"no role {role!r} in fleet {feature!r} (run `up` first)")
    msg = message or "Run `orbal-net inbox` and act on any new messages now."
    herdr("pane", "run", info["pane"], msg)
    submit(info["pane"], HARNESSES[info["harness"]])
    print(f"poked {role} ({info['pane']})")


def select_leads(roster, only=None):
    """Leads (layer 2) to spawn. `only` = comma list of lead roles; None = all.

    A roster is a catalog of teams; a mission usually needs a subset. Selecting a
    lead brings its workers along (they are gathered by parent in `up`).
    """
    leads = [r for r in roster["roles"] if r["parent"] == "orchestrator"]
    if only is None:
        return leads
    want = [t.strip() for t in only.split(",") if t.strip()]
    names = {l["role"] for l in leads}
    missing = [t for t in want if t not in names]
    if missing:
        raise ValueError(
            f"unknown team(s): {', '.join(missing)}; "
            f"available: {', '.join(sorted(names))}")
    return [l for l in leads if l["role"] in want]


def _reset_mission_state(feature):
    """Clear a prior run's orbal-net DB + log so a fresh `up` starts from clean
    coordination state. A leftover orbal-net.db (from an interrupted `down`) would
    resurrect its rooms/messages and boot the new agents onto stale instructions.
    The mid-mission server *restart* path reuses the db and does not call this.
    Leaves the mission clone (work/) untouched."""
    d = os.path.join(MISSIONS_ROOT, feature)
    for f in ("orbal-net.db", "orbal-net.db-wal", "orbal-net.db-shm", "orbal-net.log"):
        try:
            os.remove(os.path.join(d, f))
        except FileNotFoundError:
            pass


def up(roster_path, only=None):
    roster = json.load(open(roster_path))
    validate(roster)
    feature, repo = roster["feature"], roster["repo"]
    _reset_mission_state(feature)

    panes = {}
    try:
        if SANDBOX:
            mission_up(feature, repo)  # per-mission microVM: isolated clone + creds
        orbal_net_up(feature)              # authoritative host orbal-net server for this mission (all modes)
        _verify_agent_orbal_net(feature)   # fail loud now if agents can't resolve `orbal-net`
        # Seed the mission room owned by the orchestrator (the pane the human drives).
        # Leads then `join` it deterministically, and the orchestrator can `orbal-net send`
        # without a manual join step.
        orbal_net_post(feature, "orchestrator", "create-room", name=f"mission-{feature}")

        # If `/scope-mission` wrote a brief next to the roster, seed it as the mission
        # room's first message so every lead reads it (and relays it) before working.
        brief_path = os.path.join(os.path.dirname(roster_path), f"{feature}.brief.md")
        has_brief = os.path.isfile(brief_path)
        if has_brief:
            orbal_net_post(feature, "orchestrator", "send",
                       room=f"mission-{feature}", text=open(brief_path).read())

        ws = herdr("workspace", "create", "--cwd", repo, "--label", f"mission-{feature}", "--no-focus")
        workspace_id = ws["result"]["workspace"]["workspace_id"]
        root_tab = ws["result"]["tab"]["tab_id"]
        root_pane = ws["result"]["root_pane"]["pane_id"]

        leads = select_leads(roster, only)
        for i, lead in enumerate(leads):
            if i == 0:  # reuse the workspace's default tab for the first lead
                herdr("tab", "rename", root_tab, lead["role"])
                pane = root_pane
            else:
                tab = herdr("tab", "create", "--workspace", workspace_id, "--label", lead["role"])
                pane = tab["result"]["root_pane"]["pane_id"]
            launch(pane, lead["role"], lead["harness"], lead["model"], feature, "orchestrator", has_brief)
            panes[lead["role"]] = pane

            anchor = pane
            for w in [r for r in roster["roles"] if r["parent"] == lead["role"]]:
                split = herdr("pane", "split", anchor, "--direction", "right", "--no-focus")
                wp = split["result"]["pane"]["pane_id"]
                launch(wp, w["role"], w["harness"], w["model"], feature, lead["role"])
                panes[w["role"]] = wp
                anchor = wp

        # Record role -> pane so `poke`/`down` can reach agents after `up` returns.
        roles = {r["role"]: {"pane": panes[r["role"]], "parent": r["parent"], "harness": r["harness"]}
                 for r in roster["roles"] if r["role"] in panes}
        _save_state(feature, roles=roles)

        # Start the connector for each spawned eve leaf role (v0: exactly one). After
        # the launch loop so the eve pane's :3000 is already READY when it connects.
        for r in roster["roles"]:
            if r.get("harness") == "eve" and r["role"] in panes:
                orbal_net_connector_up(feature, r["role"], f"squad-{r['parent']}")
    except BaseException as e:
        # Never leave an orphan microVM / half-built workspace / server behind on a
        # failed (or interrupted) `up`; tear down whatever was started, then re-raise.
        print(f"up failed ({type(e).__name__}: {e}); tearing down partial {feature}", file=sys.stderr)
        try:
            down(feature)
        except SystemExit:
            pass  # down exits non-zero when there was nothing to close - fine here
        except Exception:
            pass
        raise
    print(json.dumps(panes))


def down(feature):
    label = f"mission-{feature}"
    # Kill the mission's orbal-net server: it is the single authority for every room
    # (mission + all squads), so killing it IS the room cleanup - no orphaned squad
    # rooms, no per-lead teardown pokes. Read the pid before state is deleted below.
    pid = _load_state(feature).get("orbal_net_pid")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # already gone (crashed / manually killed) - nothing to clean up

    # Gracefully stop the eve connector before tearing the VM down, so it fsyncs its
    # cursor. In sandbox mode the `container rm -f` in mission_down is the hard reap
    # regardless; this is the clean-shutdown-first step. Must run before state is
    # cleared below.
    orbal_net_connector_down(feature)

    closed = None
    for w in herdr("workspace", "list")["result"]["workspaces"]:
        if w.get("label") == label:
            herdr("workspace", "close", w["workspace_id"])
            closed = w["workspace_id"]
            break
    if SANDBOX:
        mission_down(feature)  # stop the microVM + wipe its secrets (also clears state)
    else:
        shutil.rmtree(os.path.join(MISSIONS_ROOT, feature), ignore_errors=True)  # drop role->pane state
    if closed:
        print(f"closed {label} ({closed})")
    else:
        sys.exit(f"no workspace labelled {label}")


def status(feature):
    """One-shot mission health: orbal-net server, container, agents, room activity.
    Replaces the manual ps/lsof/container/orbal-net dig used to diagnose a stall."""
    st = _load_state(feature)
    if not st:
        sys.exit(f"no mission state for {feature} (is it up?)")
    out = [f"mission: {feature}"]

    pid = st.get("orbal_net_pid")
    alive = bool(pid) and _pid_alive(pid)
    out.append(f"  orbal-net server: pid {pid} {'ALIVE' if alive else 'DEAD'}  {st.get('orbal_net_url','?')}")
    if not alive:
        out.append(f"    (restart: orbal-net serve --token {st.get('orbal_net_token','?')} "
                   f"--port <port-from-url> --db {os.path.join(MISSIONS_ROOT, feature, 'orbal-net.db')})")

    if SANDBOX:
        rows = subprocess.run(["container", "list"], capture_output=True, text=True).stdout.splitlines()
        row = next((r for r in rows if f"mission-{feature}" in r), None)
        out.append(f"  container: {'running' if row else 'NOT running'}")

    # eve connector liveness (silent-failure dependency; only present on eve missions).
    conn = orbal_net_connector_status(feature, st)
    if conn:
        out.append(conn)

    if alive:
        try:
            agents = orbal_net_post(feature, "orchestrator", "agents").get("agents", [])
            out.append("  agents: " + (", ".join(f"{a['id']}({a['status']})" for a in agents) or "(none)"))
            for r in orbal_net_post(feature, "orchestrator", "rooms").get("rooms", []):
                # peek (non-consuming) from seq 0 so status never eats the orchestrator's cursor
                msgs = orbal_net_post(feature, "orchestrator", "read",
                                  room=r["name"], since=0, peek=True).get("messages", [])
                last = msgs[-1] if msgs else None
                tail = f'  last[{last["seq"]}] {last["from"]}: {last["text"][:70]}' if last else ""
                out.append(f"  room {r['name']}: {len(msgs)} msgs{tail}")
        except Exception as e:
            out.append(f"  (orbal-net query failed: {e})")
    print("\n".join(out))


def selfcheck():
    ok = {"feature": "t", "repo": "/tmp", "roles": [
        {"role": "lead", "parent": "orchestrator", "harness": "claude", "model": "x"},
        {"role": "w1", "parent": "lead", "harness": "codex", "model": "x"},
    ]}
    assert set(validate(ok)) == {"lead", "w1"}

    # team selection: a roster is a catalog; a mission spawns a subset.
    catalog = {"feature": "t", "repo": "/tmp", "roles": [
        {"role": "lead-a", "parent": "orchestrator", "harness": "claude", "model": "x"},
        {"role": "lead-b", "parent": "orchestrator", "harness": "claude", "model": "x"},
        {"role": "w", "parent": "lead-a", "harness": "claude", "model": "x"},
    ]}
    assert [l["role"] for l in select_leads(catalog)] == ["lead-a", "lead-b"]
    assert [l["role"] for l in select_leads(catalog, "lead-b")] == ["lead-b"]
    try:
        select_leads(catalog, "ghost")
        assert False, "unknown team should raise"
    except ValueError:
        pass

    def rejects(roster):
        try:
            validate(roster)
            return False
        except ValueError:
            return True

    # layer 4: orchestrator -> lead -> w1 -> w2
    assert rejects({"feature": "t", "repo": "/tmp", "roles": [
        {"role": "lead", "parent": "orchestrator", "harness": "claude", "model": "x"},
        {"role": "w1", "parent": "lead", "harness": "claude", "model": "x"},
        {"role": "w2", "parent": "w1", "harness": "claude", "model": "x"},
    ]})
    # worker with a child (worker is not a leaf)
    assert rejects({"feature": "t", "repo": "/tmp", "roles": [
        {"role": "lead", "parent": "orchestrator", "harness": "claude", "model": "x"},
        {"role": "w1", "parent": "lead", "harness": "claude", "model": "x"},
        {"role": "w2", "parent": "w1", "harness": "claude", "model": "x"},
    ]})
    # unknown parent
    assert rejects({"feature": "t", "repo": "/tmp", "roles": [
        {"role": "w1", "parent": "ghost", "harness": "claude", "model": "x"},
    ]})

    # sandbox wrap: harness cmd runs inside the mission microVM (or bare when off)
    if SANDBOX:
        assert sandbox_wrap("claude --x", "t") == "container exec -it -w /work mission-t claude --x"
    else:
        assert sandbox_wrap("claude --x", "t") == "claude --x"

    # bootstrap wiring: leads join the (orchestrator-owned) mission room; workers
    # commit their file changes so harvest preserves them past teardown.
    lead_b = bootstrap("lead", "claude", "f", "orchestrator")
    assert "orbal-net join mission-f" in lead_b
    # progress emission wiring: leads emit lifecycle events to the mission room,
    # workers emit lifecycle + step/phase/blocked to their squad room.
    assert "orbal-net event mission-f task-start" in lead_b and "orbal-net event mission-f task-done" in lead_b
    wb = bootstrap("w1", "claude", "f", "lead")
    assert "orbal-net join squad-lead" in wb and "wcommit" in wb
    assert "orbal-net event squad-lead task-start" in wb and "orbal-net progress squad-lead" in wb
    # brief wiring: a lead reads+relays the brief only when one was posted
    assert "read mission-f --since 0" not in bootstrap("lead", "claude", "f", "orchestrator")
    lb = bootstrap("lead", "claude", "f", "orchestrator", has_brief=True)
    assert "read mission-f --since 0" in lb and "orbal-net send squad-lead <brief>" in lb

    # bootstrap tells agents the CLI is preinstalled (never build it from the mission repo)
    assert "do NOT build it from the mission repo" in lead_b and "do NOT build it from the mission repo" in wb

    # bridge-pr argv: --fill without a title, explicit title/body with one
    assert _pr_cmd("mission-f", None)[-1] == "--fill" and "mission-f" in _pr_cmd("mission-f", None)
    assert "--title" in _pr_cmd("mission-f", "t") and "t" in _pr_cmd("mission-f", "t")

    # eve harness: a server pane (ready on :3000, no "working" marker), launched
    # without bootstrap; its start command wipes the durable store, links the Vercel
    # TEAM scope (zico-ios-projects, not the rejected personal handle), runs eve start.
    assert HARNESSES["eve"]["ready"] == "server listening at http://127.0.0.1:3000/"
    assert HARNESSES["eve"]["working"] is None
    assert "eve start" in EVE_START_CMD and "zico-ios-projects" in EVE_START_CMD
    assert "rm -rf .workflow-data" in EVE_START_CMD
    # FIX 3: a fresh mission clone has no node_modules, so the eve pane installs deps
    # (npm ci, falling back to npm install) before building/serving.
    assert "npm ci" in EVE_START_CMD and "npm install" in EVE_START_CMD
    assert "--project bob" in EVE_START_CMD  # rebranded Vercel project
    # EVE_START_CMD passes through .format harmlessly (no placeholders to fill)
    assert HARNESSES["eve"]["cmd"].format(model="m", role="r") == EVE_START_CMD
    # connector status is a no-op line when the mission has no eve connector
    assert orbal_net_connector_status("t", {}) is None
    assert orbal_net_connector_status("t", {"eve_connector": None}) is None
    print("selfcheck ok")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["up"] and len(args) in (2, 3):
        up(args[1], args[2] if len(args) == 3 else None)
    elif args[:1] == ["poke"] and 3 <= len(args) <= 4:
        poke(args[1], args[2], args[3] if len(args) == 4 else None)
    elif args[:1] == ["status"] and len(args) == 2:
        status(args[1])
    elif args[:1] == ["bridge-pr"] and 2 <= len(args) <= 3:
        bridge_pr(args[1], args[2] if len(args) == 3 else None)
    elif args[:1] == ["down"] and len(args) == 2:
        down(args[1])
    elif args == ["selfcheck"]:
        selfcheck()
    else:
        sys.exit(__doc__)
