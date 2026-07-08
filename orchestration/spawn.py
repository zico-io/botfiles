#!/usr/bin/env python3
"""spawn.py — stand up / tear down a 3-layer agent fleet on herdr.

Reads a roster JSON, spawns leads (layer 2) as herdr tabs and workers (layer 3)
as pane splits inside their lead's tab, launches each harness binary, waits for
it to be ready, then injects a bootstrap prompt that registers the agent into
agent-comms and joins its room.

herdr owns placement/process/status; agent-comms owns coordination. The
orchestrator is layer 1 — the pane you are already in — and is NOT spawned here.

Usage:
  python3 spawn.py up   <roster.json>          # spawns fleet, prints {role: pane_id} JSON
  python3 spawn.py poke <feature> <role> [msg] # wake an idle agent (comms nudges don't auto-submit)
  python3 spawn.py down <feature>              # tears down squad rooms + closes the workspace
  python3 spawn.py selfcheck                   # asserts the layer/hierarchy rules

See orchestration/roster.example.json and .claude/commands/spawn-team.md.
"""
import json
import os
import shutil
import subprocess
import sys
import time

# Per-harness launch template + a startup substring herdr waits for before we
# inject the bootstrap prompt. {model}/{role} are filled per role.
# ponytail: ready strings and flags are version-sensitive — tune here if a
# harness changes its startup banner or the `--model` flag.
HARNESSES = {
    "claude": {"cmd": "claude --dangerously-skip-permissions --model {model}", "ready": "bypass permissions on", "working": "esc to interrupt"},
    "codex":  {"cmd": "codex --dangerously-bypass-approvals-and-sandbox --model {model}", "ready": "Codex", "working": "esc to interrupt"},
    "pi":     {"cmd": "pi --name {role} --model {model}", "ready": "pi", "working": "esc to interrupt"},
}

READY_TIMEOUT_MS = "90000"  # ponytail: cold microVM start; raise if the VM/host gets slower
SUBMIT_TIMEOUT_MS = "15000"  # how long to wait for an injected prompt to start running
SQUAD_CLEANUP_WAIT_S = 8     # grace for leads to destroy their own squad room at teardown

# Sandbox: run each mission inside one Apple `container` microVM (per-mission
# granularity). Agents attach as `container exec` processes, so herdr's PTY
# (banner match + send-keys) and the in-guest agent-comms mesh work unchanged.
# Default ON; BOTFILE_NO_SANDBOX=1 runs bare on the host (debugging only).
# See .botfile/memory/tools/sandbox.md and sandbox/build.sh.
SANDBOX = os.environ.get("BOTFILE_NO_SANDBOX") != "1"
CONTAINER_IMAGE = "botfiles-agent"
SECRETS_ROOT = "/tmp/botfile-secrets"
MISSIONS_ROOT = "/tmp/botfile-missions"  # per-mission clone + state, keyed by feature


def container(*args, check=True):
    """Run an Apple `container` CLI command; return stdout stripped."""
    return subprocess.run(["container", *args], capture_output=True, text=True, check=check).stdout.strip()


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
    print(f"warning: could not harvest {branch}: {r.stderr.strip()}", file=sys.stderr)
    return False


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


def mission_up(feature, repo):
    """Start the per-mission microVM: isolated clone at /work, creds at /secrets."""
    name = f"mission-{feature}"
    container("rm", "-f", name, check=False)  # clear any stale container
    workdir = mission_workdir(feature, repo)
    secrets = mission_secrets(feature)
    container("run", "-d", "--name", name,
              "-v", f"{workdir}:/work", "-v", f"{secrets}:/secrets:ro", "-w", "/work",
              CONTAINER_IMAGE, "sleep", "infinity")
    # The image ships credentials but a fresh claude still blocks on three
    # first-run prompts that --dangerously-skip-permissions does NOT skip:
    # the theme picker, the /work folder-trust dialog, and the bypass-mode
    # acceptance. Pre-answer all three so the TUI boots straight to ready.
    # Idempotent; harmless for codex-only missions.
    container("exec", name, "python3", "-c", CLAUDE_SEED)
    os.makedirs(os.path.dirname(_state_path(feature)), exist_ok=True)
    json.dump({"repo": repo, "workdir": workdir}, open(_state_path(feature), "w"))
    return name


def mission_down(feature):
    container("rm", "-f", f"mission-{feature}", check=False)
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


def sandbox_wrap(cmd, feature):
    """Wrap a harness command so it runs inside the mission's microVM."""
    return f"container exec -it -w /work mission-{feature} {cmd}" if SANDBOX else cmd


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


def bootstrap(role, harness, feature, parent):
    """First-turn prompt: register into agent-comms and join the right room."""
    mission = f"mission-{feature}"
    if parent == "orchestrator":  # lead (layer 2)
        squad = f"squad-{role}"
        return (
            f"You are '{role}', a {harness} agent in mission '{feature}', parent orchestrator. "
            f"Using the agent-comms tool: register as '{role}', join_room '{mission}', and "
            f"create_room '{squad}' (public). Announce ready in '{mission}'. Await tasks in "
            f"'{mission}', delegate to your workers in '{squad}', and report results up to "
            f"'{mission}'. Never spawn agents below layer 3."
        )
    squad = f"squad-{parent}"  # worker (layer 3)
    return (
        f"You are '{role}', a {harness} agent, parent '{parent}'. Using the agent-comms tool: "
        f"register as '{role}' and join_room '{squad}'. Announce ready in '{squad}'. Do the "
        f"tasks posted there, report results back in the room, and set your status to done. "
        f"You are a leaf — do not spawn agents."
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
        herdr("wait", "output", pane, "--match", spec["working"], "--timeout", SUBMIT_TIMEOUT_MS)


def launch(pane, role, harness, model, feature, parent):
    """Run the harness in `pane`, wait for it to be ready, inject the bootstrap."""
    spec = HARNESSES[harness]
    herdr("pane", "run", pane, sandbox_wrap(spec["cmd"].format(model=model, role=role), feature))
    herdr("wait", "output", pane, "--match", spec["ready"], "--timeout", READY_TIMEOUT_MS)
    herdr("pane", "run", pane, bootstrap(role, harness, feature, parent))
    submit(pane, spec)


def poke(feature, role, message=None):
    """Wake an idle agent by submitting a prompt straight into its pane.

    agent-comms room messages are typed into an idle Claude agent's input but NOT
    submitted (the bridge never sends the newline), so a delegated agent can sit idle
    forever with the nudge unsent. `herdr pane run` types AND submits, which wakes it.
    This is a herdr/PTY-level nudge, not an agent-comms message, so it does not put the
    orchestrator into a worker's room - the hierarchy holds. In sandbox mode only the
    host can reach herdr, so pokes originate from the orchestrator. Use whenever a
    target didn't act on a room message.
    """
    st = _load_state(feature)
    info = (st.get("roles") or {}).get(role)
    if not info:
        sys.exit(f"no role {role!r} in fleet {feature!r} (run `up` first)")
    msg = message or "Check your agent-comms rooms for new messages and act on them now."
    herdr("pane", "run", info["pane"], msg)
    submit(info["pane"], HARNESSES[info["harness"]])
    print(f"poked {role} ({info['pane']})")


COORDINATOR_PORT = "19876"  # agent-comms mesh: first bridge to bind it coordinates.


def preflight_coordinator():
    """Abort if a STOPPED process holds the agent-comms coordinator port.

    A suspended (SIGSTOP'd) bridge keeps port 19876 bound but never accepts new
    peers, so every bridge that starts afterward times out and falls back to its
    own island — the whole fleet silently fails to mesh. lsof -sTCP:LISTEN gives
    the owning pid; `ps -o stat` starting with 'T' means stopped.
    """
    out = subprocess.run(["lsof", "-nP", "-iTCP:" + COORDINATOR_PORT, "-sTCP:LISTEN", "-t"],
                         capture_output=True, text=True).stdout.split()
    for pid in out:
        stat = subprocess.run(["ps", "-o", "stat=", "-p", pid], capture_output=True, text=True).stdout.strip()
        if stat.startswith("T"):
            sys.exit(f"coordinator port {COORDINATOR_PORT} held by STOPPED pid {pid} (stat {stat}); "
                     f"a suspended bridge poisons the mesh — run `kill -9 {pid}` and re-spawn.")


def up(roster_path):
    roster = json.load(open(roster_path))
    validate(roster)
    feature, repo = roster["feature"], roster["repo"]

    if SANDBOX:
        mission_up(feature, repo)  # the agent-comms mesh lives inside this VM now
    else:
        preflight_coordinator()    # bare mode: the mesh binds a host port

    ws = herdr("workspace", "create", "--cwd", repo, "--label", f"mission-{feature}", "--no-focus")
    workspace_id = ws["result"]["workspace"]["workspace_id"]
    root_tab = ws["result"]["tab"]["tab_id"]
    root_pane = ws["result"]["root_pane"]["pane_id"]

    panes = {}
    leads = [r for r in roster["roles"] if r["parent"] == "orchestrator"]
    for i, lead in enumerate(leads):
        if i == 0:  # reuse the workspace's default tab for the first lead
            herdr("tab", "rename", root_tab, lead["role"])
            pane = root_pane
        else:
            tab = herdr("tab", "create", "--workspace", workspace_id, "--label", lead["role"])
            pane = tab["result"]["root_pane"]["pane_id"]
        launch(pane, lead["role"], lead["harness"], lead["model"], feature, "orchestrator")
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
    print(json.dumps(panes))


def down(feature):
    label = f"mission-{feature}"
    # squad-<lead> rooms are owned by the lead, not the orchestrator, and a dead pane
    # lingers as an offline member keeping the room alive - so nobody can clean them up
    # after the fact. Poke each lead to destroy its own squad while it is still running.
    # Best-effort: a crashed/unreachable lead just leaves its squad orphaned (no worse
    # than before). The mission-<feature> room is orchestrator-owned; the orchestrator
    # destroys it via agent-comms after `down` returns.
    roles = _load_state(feature).get("roles", {})
    poked = False
    for role, info in roles.items():
        if info.get("parent") == "orchestrator":
            try:
                poke(feature, role,
                     f"Teardown: use the agent-comms tool to destroy_room 'squad-{role}', "
                     f"then leave every room and stop.")
                poked = True
            except subprocess.CalledProcessError as e:
                print(f"warn: lead {role!r} unreachable; squad-{role} may linger ({e})", file=sys.stderr)
    if poked:
        time.sleep(SQUAD_CLEANUP_WAIT_S)  # ponytail: fixed grace for leads to run destroy_room

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


def selfcheck():
    ok = {"feature": "t", "repo": "/tmp", "roles": [
        {"role": "lead", "parent": "orchestrator", "harness": "claude", "model": "x"},
        {"role": "w1", "parent": "lead", "harness": "codex", "model": "x"},
    ]}
    assert set(validate(ok)) == {"lead", "w1"}

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
    print("selfcheck ok")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["up"] and len(args) == 2:
        up(args[1])
    elif args[:1] == ["poke"] and 3 <= len(args) <= 4:
        poke(args[1], args[2], args[3] if len(args) == 4 else None)
    elif args[:1] == ["down"] and len(args) == 2:
        down(args[1])
    elif args == ["selfcheck"]:
        selfcheck()
    else:
        sys.exit(__doc__)
