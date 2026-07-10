# Reference for mission bob-cli (THROWAWAY - remove before the final RFC PR)

The mission clone is .botfiles, so the BOB-repo (zico-io/bob) files you must ground in are
copied here under reference/bob-repo/ (bin-bob.sh = bin/bob, the launcher; package.json + the
eve build scripts; agent/sandbox.ts = the microsandbox pin; agent/lib/host-exec.ts = how the
spawn_* tools resolve ORCHESTRATION_DIR; the spawn_*/plan_pane_*/herdr_pane_read tools;
docs/HOST-RUN-PLAYBOOK.md = the CURRENT manual UX this RFC replaces; HOST-SHAKEDOWN.md).
- bob-orchestrator.rfc.md = the L1-orchestrator design of record.
- spawn.py, plan_pane.py, AGENTS.md are ALREADY in this clone at their real paths
  (orchestration/, .botfile/... , root) - read them there, they are the source of truth for
  the spawn.py-ownership question.

Deliverable is orchestration/bob-cli.rfc.md ONLY. Remove reference/ before the final PR.
