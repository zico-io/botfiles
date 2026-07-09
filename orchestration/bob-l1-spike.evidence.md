# bob-l1-spike evidence: the two new bets of the bob-orchestrator RFC hold

Mission bob-l1-spike / RFC S9 steps 1-3, S10. Run 2026-07-09.
Throwaway local bob L1 eve project (`eve@0.22.1`, Node 24, AI Gateway via
`vercel link`), reusing the proven leaf channel/tools/connector. Goal: falsify or
confirm the TWO claims genuinely new relative to the proven leaf worker.
Result: **both GO.** No em dashes.

## Bet 1 - durable interactive session rehydrate (Proof A): GO / PASS

A thin raw session-stream client (no `@ai-sdk/tui`, no `runAgentTUI`) on the
stable host-derivable token `bob:<host>`, over a custom human channel that reuses
the proven `send(text, {continuationToken})` deliver-or-start mechanic.

```
codeword=CW-jrb19u88
SCENARIO 1 restart-keep  (hard kill + restart, .workflow-data kept):
  sessionId=wrun_01KX4DWAAEVM9CNDPMK5GA0815 (SAME)  recall="CW-jrb19u88"  history 3->4 intact
SCENARIO 2 fresh-build   (rm -rf .output; eve build; restart; .workflow-data kept):
  sessionId=wrun_01KX4DWAAEVM9CNDPMK5GA0815 (SAME)  recall="CW-jrb19u88"  history 4->5 intact
PROOF A: PASS
```
The same durable session resumes across a process restart AND a fresh build;
full history intact, codeword recalled. Resume, not restart. The RFC's #1 risk
(no fetched doc showed a terminal client cleanly riding a durable eve session) is
retired for the local case: a thin session-stream client rides it end to end.

Finding: the first POST in the narrow window right after restart/redeploy can
fail at the transport level (port up before the Workflow store finishes
rehydrating); a resuming client needs a bounded retry (added:
`fetchWithRehydrateRetry`, mirrors the leaf connector's `postFrameWithRetry`).

## Bet 2 - the notify_human multiplex (Proof B): GO / PASS

One agent, two concurrent sessions on DIFFERENT tokens (human `bob:<host>` +
mission-room `orbal-net:<room>:bob`). A room turn calls `notify_human`, relaying
into the live human session.

```
HAPPY PATH (1 frame via REAL connector + orbal-net server, 3 via direct inject):
  all 4 relays: count=1 each, indices 1,2,3,4  ->  exactlyOnce=true  ordered=true
RACE CASE (relay frame fired WHILE the human session is mid-turn, RFC S10 #2):
  humanTurnSent=+0ms  raceFrameSent=+502ms  bothSettled=+5096ms
  humanTurnOk=true  roomTurnOk=true  raceMarkerCount=1  (relay idx 6 AFTER slow human idx 5)
  exactlyOnce=true  mitigation=none needed
PROOF B: PASS
```
The relay lands exactly once and in order across both sessions, including the
mid-turn race: eve SERIALIZED the concurrent deliver into `bob:<host>` (relay
ordered after the in-flight human turn), no loss/dup/interleave. The RFC's #2
unknown resolves in favor of the design.

Nuance: exactly-once held with the process up throughout; the leaf caveat "eve
does not DURABLY queue concurrent deliveries to one token" still means a crash
between the human turn and the serialized relay could lose it, so production
`notify_human` should carry the same rehydrate/retry discipline (park-gate is a
cheap robustness belt). Hardening item, not a falsification.

Secondary (security-relevant): bob's room agent CORRECTLY refused a scripted
"call the tool with this exact text" room frame as a prompt injection; the proof
was reworked to deliver realistic lead reports that bob relays of its own
judgement. The multiplex is a judged relay, not a dumb pipe.

## Verdict

Both genuinely-new bets of the bob-orchestrator RFC's first increment are
**GO**. The interactive-orchestrator direction is sound enough to justify a real
build. Two hardening items to carry: the rehydrate retry (both bets) and a
park-gate on `notify_human` (bet 2). Everything else the RFC leans on is already
proven at the leaf (native channel, connector exactly-once/cursor/resume,
indistinguishability - bob-demo) and was reused, not re-proven.
