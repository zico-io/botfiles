#!/usr/bin/env bash
# bob - launch the bob harness via CLI (RFC S4.2 "launching bob is attach-or-create").
#
# One harness, two roles (L1-DESIGN.md section 1); this launcher owns the L1
# topology (the leaf role is launched by spawn.py's eve harness in a squad room,
# unchanged). Role via BOB_ROLE (default l1).
#
#   bob              # L1: bring the stack up (if needed) and attach the all-day TUI
#   bob up           # L1: start the shared orbal-net server + eve(:3000, RESUME) +
#                    #     the L1 connector, in the background
#   bob tui          # attach the terminal client to the durable bob:<host> session
#   bob status       # show shared-server + eve + connector up/down
#   bob down         # stop THIS bob process (eve + connector). Does NOT tear down any
#                    # mission (that is spawn_down, approval-gated) and does NOT stop the
#                    # shared server (it outlives a single bob restart) - only stops bob.
#   bob server-down  # stop the shared orbal-net server (every mission loses coordination)
#
# Shared-server model (gap #1): bob owns ONE persistent host-level `orbal-net serve`
# for ALL missions and exports its ORBAL_NET_URL/ORBAL_NET_TOKEN to eve + the
# connector, so the connector boots against a real server even with zero mission
# rooms. spawn.py's mission `up` CREATES that mission's rooms on this shared server
# (opt-in via the ORBAL_NET_SHARED_* trigger this launcher exports) instead of
# spawning a per-mission server.
#
# Process control is cross-platform (gap #2): `/proc` on linux (incl. the mission
# VM), `pgrep`/`kill` on darwin (the host) - see proc_kill. `eve start` RESUMES
# durable sessions - the launcher never wipes .workflow-data (that would destroy the
# all-day conversation). No em dashes - use "-".
#
# LAN advertise (gap #4): the shared server binds all interfaces (orbal-net serve
# always binds 0.0.0.0), but a SANDBOX/VM mission agent can't reach the host's
# loopback address. ORBAL_NET_URL (eve's in-turn tools + the connector, both
# host-side) stays 127.0.0.1; ORBAL_NET_SHARED_URL (what spawn.py's mission `up`
# records and hands to agents) is advertised on the LAN egress IP instead - see
# advertise_host, the same UDP-connect trick and override var
# (ORBAL_NET_ADVERTISE_HOST) as spawn.py's own _advertise_host().
set -u
cd "$(dirname "$0")/.." || exit 1   # -> project root

PORT="${EVE_PORT:-3000}"
EVE_LOG="${BOB_EVE_LOG:-.bob-eve.log}"
CONN_LOG="${CONNECTOR_LOG_PATH:-orbal-net-connector.log}"
export ORBAL_NET_AGENT="orchestrator"     # S8: the L1 seat is ALWAYS `orchestrator`
#                                           (spawn.py hardcodes it; leads' bootstrap
#                                           references it) - never the launching handle
export BOB_HOST_IDENTITY="${BOB_HOST_IDENTITY:-$(hostname 2>/dev/null || echo local-host)}"
export BOB_ROLE="${BOB_ROLE:-l1}"
export EVE_URL="${EVE_URL:-http://127.0.0.1:${PORT}}"
export EVE_SELF_URL="${EVE_SELF_URL:-http://127.0.0.1:${PORT}}"
export CONNECTOR_CONTROL_PORT="${CONNECTOR_CONTROL_PORT:-3900}"
export ORBAL_NET_ROOMS="${ORBAL_NET_ROOMS:-}"                 # fresh launch drives no mission yet;
#                                                              spawn_up attaches rooms on the live connector

# --- shared host-level orbal-net server (gap #1) ---------------------------
# bob (L1) owns ONE persistent orbal-net server for ALL missions. It OUTLIVES
# `bob down` (a single bob restart must not drop live missions); tear it down
# explicitly with `bob server-down`. The token is persisted so a re-bind to an
# already-running server uses the same creds; the db persists rooms/messages
# across a server restart.
ORBAL_NET_PORT="${ORBAL_NET_PORT:-4100}"
SERVER_TOKEN_FILE="${BOB_ORBAL_NET_TOKEN_FILE:-.bob-orbal-net.token}"
SERVER_DB="${BOB_ORBAL_NET_DB:-.bob-orbal-net.db}"
SERVER_LOG="${BOB_ORBAL_NET_LOG:-.bob-orbal-net.log}"

eve_up()    { curl -s --max-time 2 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; }
conn_up()   { curl -s --max-time 2 "http://127.0.0.1:${CONNECTOR_CONTROL_PORT}/control/subscriptions" >/dev/null 2>&1; }
# The shared server answers every HTTP request (401 without a token) once bound,
# so "curl connected at all" is the liveness signal - do not pass --fail.
server_up() { curl -s --max-time 2 -o /dev/null "http://127.0.0.1:${ORBAL_NET_PORT}/" >/dev/null 2>&1; }

# Portable process control (gap #2): kill every process whose full command line
# contains SUBSTRING (a plain substring, not a glob). Linux - including the
# mission VM, which has no pgrep - keeps the proven /proc scan byte-for-byte;
# darwin (the host) has no /proc, so it uses `pgrep -f` + `kill`. Never signals
# this launcher itself ($$).
proc_kill() {
  pat=$1
  if [ -d /proc ]; then
    for p in /proc/[0-9]*; do
      pid=${p#/proc/}; [ "$pid" = "$$" ] && continue
      cmd=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null) || continue
      case "$cmd" in *"$pat"*) kill -9 "$pid" 2>/dev/null ;; esac
    done
  else
    for pid in $(pgrep -f "$pat" 2>/dev/null); do
      [ "$pid" = "$$" ] && continue
      kill -9 "$pid" 2>/dev/null
    done
  fi
}

advertise_host() {
  # Primary IP that guests/remote containers can reach the host on (not loopback).
  # Mirrors spawn.py's _advertise_host() byte-for-byte (same override var, same
  # UDP-connect trick - no packet is actually sent). python3 is already a hard
  # dependency of spawn.py, so relying on it here adds nothing new.
  if [ -n "${ORBAL_NET_ADVERTISE_HOST:-}" ]; then
    printf '%s' "$ORBAL_NET_ADVERTISE_HOST"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c '
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("8.8.8.8", 80))
    print(s.getsockname()[0])
except OSError:
    print("127.0.0.1")
finally:
    s.close()
'
    return
  fi
  printf '127.0.0.1'
}

server_token() {
  # Stable token so a re-bind to an already-running server uses the same creds.
  # od/tr are present on darwin + linux (no external deps).
  if [ ! -f "$SERVER_TOKEN_FILE" ]; then
    ( umask 077; od -An -N16 -tx1 /dev/urandom | tr -d ' \n' > "$SERVER_TOKEN_FILE" )
  fi
  cat "$SERVER_TOKEN_FILE"
}

start_server() {
  local token; token=$(server_token)
  if server_up; then
    echo "[bob] shared orbal-net server already up on :${ORBAL_NET_PORT}"
  else
    echo "[bob] starting shared orbal-net server (:${ORBAL_NET_PORT}, db ${SERVER_DB})..."
    nohup orbal-net serve --token "$token" --port "$ORBAL_NET_PORT" --db "$SERVER_DB" >"$SERVER_LOG" 2>&1 &
    for i in $(seq 1 30); do server_up && break; sleep 1; done
    server_up || { echo "[bob] shared server FAILED to start; log tail:" >&2; tail -20 "$SERVER_LOG" >&2; return 1; }
    echo "[bob] shared server ready"
  fi
  # Coords for the connector + eve's in-turn tools (host-side, loopback is
  # correct and fastest), plus the DEDICATED trigger that flips spawn.py to the
  # additive "use existing server" path. ORBAL_NET_SHARED_URL is what spawn.py
  # records for mission agents (gap #4) - advertise the LAN egress IP there so
  # a SANDBOX/VM agent can dial in; the server itself already binds 0.0.0.0, so
  # this only changes the advertised address, not the bind. The trigger is a
  # distinct var pair so the legacy claude-L1 path (which never sets it) stays
  # byte-for-byte a per-mission server.
  export ORBAL_NET_URL="http://127.0.0.1:${ORBAL_NET_PORT}"
  export ORBAL_NET_TOKEN="$token"
  export ORBAL_NET_SHARED_URL="http://$(advertise_host):${ORBAL_NET_PORT}"
  export ORBAL_NET_SHARED_TOKEN="$token"
}

need_deps() { [ -d node_modules/eve ] || { echo "[bob] installing deps..."; npm ci || npm install; }; }
need_build() { [ -f .output/server/index.mjs ] || { echo "[bob] building..."; npx eve build; }; }
need_env() {
  if [ ! -f .env.local ]; then
    echo "[bob] .env.local missing - run: vercel link --yes --scope zico-ios-projects --project bob" >&2
    echo "[bob] (writes a fresh VERCEL_OIDC_TOKEN so eve reaches the AI Gateway)" >&2
    return 1
  fi
}

start_eve() {
  if eve_up; then echo "[bob] eve already up on :${PORT}"; return 0; fi
  need_deps; need_env || return 1; need_build
  echo "[bob] starting eve (RESUME durable sessions, identity=${ORBAL_NET_AGENT}, host=${BOB_HOST_IDENTITY})..."
  nohup npx eve start >"$EVE_LOG" 2>&1 &
  for i in $(seq 1 90); do
    if grep -q "server listening" "$EVE_LOG" 2>/dev/null && eve_up; then echo "[bob] eve ready after ${i}s"; return 0; fi
    sleep 1
  done
  echo "[bob] eve FAILED to start; log tail:" >&2; tail -20 "$EVE_LOG" >&2; return 1
}

start_connector() {
  if conn_up; then echo "[bob] connector already up (control :${CONNECTOR_CONTROL_PORT})"; return 0; fi
  echo "[bob] starting L1 connector (control :${CONNECTOR_CONTROL_PORT}, shared server ${ORBAL_NET_URL}, initial rooms='${ORBAL_NET_ROOMS}')..."
  nohup node --experimental-strip-types connector/main.ts >>"$CONN_LOG" 2>&1 &
  for i in $(seq 1 30); do conn_up && { echo "[bob] connector ready after ${i}s"; return 0; }; sleep 1; done
  echo "[bob] connector FAILED to start; log tail:" >&2; tail -20 "$CONN_LOG" >&2; return 1
}

cmd_up()     { start_server && start_eve && start_connector; }
# The durable front end entry is a seam (gap #5): the default is the proven thin
# client; the AI SDK 7 TUI / eve-client front end drops in by pointing BOB_TUI_ENTRY
# (or flipping this default) at its entry once it lands - both ride the same durable
# bob:<host> session, so the launcher shape does not change.
cmd_tui()    { exec node --experimental-strip-types "${BOB_TUI_ENTRY:-client/bob-tui.ts}"; }
cmd_status() {
  echo "shared-server: $(server_up && echo "up (:${ORBAL_NET_PORT})" || echo down)  eve: $(eve_up && echo up || echo down)  connector: $(conn_up && echo up || echo down)"
}
cmd_down() {
  echo "[bob] stopping bob (eve + connector); missions and the shared server are NOT torn down (use 'bob server-down' for the server)"
  proc_kill 'connector/main.ts'
  proc_kill 'eve start'; proc_kill '.output/server/index'
  sleep 1; cmd_status
}
cmd_server_down() {
  echo "[bob] stopping the SHARED orbal-net server (every mission loses coordination)"
  proc_kill 'orbal-net serve'
  sleep 1
  server_up && { echo "[bob] WARNING: shared server still up on :${ORBAL_NET_PORT}" >&2; return 1; } || echo "[bob] shared server down"
}

case "${1:-}" in
  up)          cmd_up ;;
  tui)         cmd_tui ;;
  status)      cmd_status ;;
  down)        cmd_down ;;
  server-down) cmd_server_down ;;
  ""|start)    cmd_up && cmd_tui ;;
  *) echo "usage: bob [up|tui|status|down|server-down]" >&2; exit 2 ;;
esac
