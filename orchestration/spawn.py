#!/usr/bin/env python3
"""spawn.py — stand up / tear down a 3-layer agent fleet on herdr.

Reads a roster JSON, spawns leads (layer 2) as herdr tabs and workers (layer 3)
as pane splits inside their lead's tab, launches each harness binary, waits for
it to be ready, then injects a bootstrap prompt that registers the agent into
agent-comms and joins its room.

herdr owns placement/process/status; agent-comms owns coordination. The
orchestrator is layer 1 — the pane you are already in — and is NOT spawned here.

Usage:
  python3 spawn.py up   <roster.json>   # spawns fleet, prints {role: pane_id} JSON
  python3 spawn.py down <feature>       # closes the mission-<feature> workspace
  python3 spawn.py selfcheck            # asserts the layer/hierarchy rules

See orchestration/roster.example.json and .claude/commands/spawn-team.md.
"""
import json
import os
import shutil
import subprocess
import sys

# Per-harness launch template + a startup substring herdr waits for before we
# inject the bootstrap prompt. {model}/{role} are filled per role.
# ponytail: ready strings and flags are version-sensitive — tune here if a
# harness changes its startup banner or the `--model` flag.
HARNESSES = {
    "claude": {"cmd": "claude --dangerously-skip-permissions --model {model}", "ready": "bypass permissions on", "working": "esc to interrupt"},
    "codex":  {"cmd": "codex --dangerously-bypass-approvals-and-sandbox --model {model}", "ready": "Codex", "working": "esc to interrupt"},
    "pi":     {"cmd": "pi --name {role} --model {model}", "ready": "pi", "working": "esc to interrupt"},
}

READY_TIMEOUT_MS = "60000"
SUBMIT_TIMEOUT_MS = "15000"  # how long to wait for an injected prompt to start running

# Sandbox: run each mission inside one Apple `container` microVM (per-mission
# granularity). Agents attach as `container exec` processes, so herdr's PTY
# (banner match + send-keys) and the in-guest agent-comms mesh work unchanged.
# Default ON; BOTFILE_NO_SANDBOX=1 runs bare on the host (debugging only).
# See .botfile/memory/tools/sandbox.md and sandbox/build.sh.
SANDBOX = os.environ.get("BOTFILE_NO_SANDBOX") != "1"
CONTAINER_IMAGE = "botfiles-agent"
SECRETS_ROOT = "/tmp/botfile-secrets"


def container(*args, check=True):
    """Run an Apple `container` CLI command; return stdout stripped."""
    return subprocess.run(["container", *args], capture_output=True, text=True, check=check).stdout.strip()


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


def mission_up(feature, repo):
    """Start the per-mission microVM: repo at /work, creds read-only at /secrets."""
    name = f"mission-{feature}"
    container("rm", "-f", name, check=False)  # clear any stale container
    secrets = mission_secrets(feature)
    container("run", "-d", "--name", name,
              "-v", f"{repo}:/work", "-v", f"{secrets}:/secrets:ro", "-w", "/work",
              CONTAINER_IMAGE, "sleep", "infinity")
    return name


def mission_down(feature):
    container("rm", "-f", f"mission-{feature}", check=False)
    shutil.rmtree(os.path.join(SECRETS_ROOT, feature), ignore_errors=True)


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


def launch(pane, role, harness, model, feature, parent):
    """Run the harness in `pane`, wait for it to be ready, inject the bootstrap."""
    spec = HARNESSES[harness]
    herdr("pane", "run", pane, sandbox_wrap(spec["cmd"].format(model=model, role=role), feature))
    herdr("wait", "output", pane, "--match", spec["ready"], "--timeout", READY_TIMEOUT_MS)
    herdr("pane", "run", pane, bootstrap(role, harness, feature, parent))
    # A freshly-split pane can swallow the submit newline before its TUI is ready,
    # leaving the prompt typed but unsent. Confirm the agent started; if not, press
    # Enter and re-check. An extra Enter on an already-submitted (empty) prompt is a
    # harmless no-op, so this is safe to run for every agent.
    try:
        herdr("wait", "output", pane, "--match", spec["working"], "--timeout", SUBMIT_TIMEOUT_MS)
    except subprocess.CalledProcessError:
        herdr("pane", "send-keys", pane, "Enter")
        herdr("wait", "output", pane, "--match", spec["working"], "--timeout", SUBMIT_TIMEOUT_MS)


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

    print(json.dumps(panes))


def down(feature):
    label = f"mission-{feature}"
    closed = None
    for w in herdr("workspace", "list")["result"]["workspaces"]:
        if w.get("label") == label:
            herdr("workspace", "close", w["workspace_id"])
            closed = w["workspace_id"]
            break
    if SANDBOX:
        mission_down(feature)  # stop the microVM + wipe its secrets, always
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
    elif args[:1] == ["down"] and len(args) == 2:
        down(args[1])
    elif args == ["selfcheck"]:
        selfcheck()
    else:
        sys.exit(__doc__)
