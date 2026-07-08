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
    herdr("pane", "run", pane, spec["cmd"].format(model=model, role=role))
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


def up(roster_path):
    roster = json.load(open(roster_path))
    validate(roster)
    feature, repo = roster["feature"], roster["repo"]

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
    for w in herdr("workspace", "list")["result"]["workspaces"]:
        if w.get("label") == label:
            herdr("workspace", "close", w["workspace_id"])
            print(f"closed {label} ({w['workspace_id']})")
            return
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
