#!/usr/bin/env python3
"""comms_server.py - authoritative per-mission coordination server (host-side).

Replaces the agent-comms peer-to-peer mesh with a single source of truth: one
server per mission, on the host, holding all agents / rooms / messages in memory.
Agents (host orchestrator and in-VM leads/workers) talk to it over TCP with the
stdlib `comms` client (bin/comms). This structurally kills the three mesh bugs:
one authority (no islanding), rooms owned by a server that is killed at teardown
(no orphaned squad rooms), and no lost-message class.

State is in-memory only - the server's lifetime IS the mission's, so there is
nothing to persist; `spawn.py down` kills it and every room vanishes with it.

Transport: JSON-over-HTTP, one path per action, Bearer-token auth (the server is
network-exposed on 0.0.0.0 so local-NAT and future remote containers can dial in;
the token replaces the mesh's implicit localhost trust). Identity is the caller's
`agent` field (from COMMS_AGENT); unknown agents are upserted on first call.

Usage:
  python3 comms_server.py --token <t> [--port N]   # serve; prints {"port": N} first
  python3 comms_server.py --demo                    # in-process self-check
"""
import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATES = {"active", "idle", "busy", "done"}


class Store:
    """All mission coordination state, guarded by one lock (handlers are threaded)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.agents = {}          # id -> {"status": str}
        self.rooms = {}           # name -> {"owner": str, "type": str, "members": set}
        self.messages = {}        # room-key -> [ {"seq": int, "from": str, "text": str} ]
        self.cursors = {}         # (agent, room-key) -> last seq consumed via read
        self._seq = 0

    def touch(self, agent):
        """Implicit register: ensure the agent exists (upsert on first contact)."""
        self.agents.setdefault(agent, {"status": "active"})

    def _next_seq(self):
        self._seq += 1
        return self._seq

    def _append(self, room_key, sender, text):
        msg = {"seq": self._next_seq(), "from": sender, "text": text}
        self.messages.setdefault(room_key, []).append(msg)
        return msg

    @staticmethod
    def dm_key(a, b):
        return "@" + "|".join(sorted((a, b)))

    def relevant_rooms(self, agent):
        """Room keys the agent should see in its inbox: joined rooms + its DMs."""
        keys = [n for n, r in self.rooms.items() if agent in r["members"]]
        keys += [k for k in self.messages if k.startswith("@") and agent in k[1:].split("|")]
        return keys

    def unread(self, agent, room_key):
        cur = self.cursors.get((agent, room_key), 0)
        return [m for m in self.messages.get(room_key, []) if m["seq"] > cur]


class Err(Exception):
    """Raise to return an HTTP error with a status code and message."""
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def _require(body, *fields):
    for f in fields:
        if not body.get(f):
            raise Err(400, f"missing field {f!r}")
    return [body[f] for f in fields]


# Each op takes (store, body) and returns a JSON-serializable dict. The store lock
# is already held. Identity (body["agent"]) is upserted by the handler before dispatch.
def op_register(s, b):
    return {"ok": True, "agent": b["agent"]}


def op_whoami(s, b):
    return {"agent": b["agent"], "status": s.agents[b["agent"]]["status"]}


def op_agents(s, b):
    return {"agents": [{"id": a, "status": v["status"]} for a, v in sorted(s.agents.items())]}


def op_status(s, b):
    (state,) = _require(b, "state")
    if state not in STATES:
        raise Err(400, f"bad state {state!r}; want one of {sorted(STATES)}")
    s.agents[b["agent"]]["status"] = state
    return {"ok": True, "status": state}


def op_create_room(s, b):
    (name,) = _require(b, "name")
    rtype = b.get("type") or "public"
    existing = s.rooms.get(name)
    if existing:
        if existing["owner"] != b["agent"]:
            raise Err(409, f"room {name!r} already exists (owner {existing['owner']!r})")
        return {"ok": True, "room": name, "owner": existing["owner"]}  # idempotent for owner
    s.rooms[name] = {"owner": b["agent"], "type": rtype, "members": {b["agent"]}}
    return {"ok": True, "room": name, "owner": b["agent"]}


def op_rooms(s, b):
    return {"rooms": [{"name": n, "type": r["type"], "owner": r["owner"],
                       "members": sorted(r["members"])} for n, r in sorted(s.rooms.items())]}


def _room(s, name):
    r = s.rooms.get(name)
    if not r:
        raise Err(404, f"no room {name!r}")
    return r


def op_join(s, b):
    (room,) = _require(b, "room")
    _room(s, room)["members"].add(b["agent"])
    return {"ok": True, "room": room}


def op_leave(s, b):
    (room,) = _require(b, "room")
    _room(s, room)["members"].discard(b["agent"])
    return {"ok": True, "room": room}


def op_destroy_room(s, b):
    (room,) = _require(b, "room")
    r = _room(s, room)
    if r["owner"] != b["agent"]:
        raise Err(403, f"not owner of {room!r} (owner {r['owner']!r})")
    s.rooms.pop(room, None)
    s.messages.pop(room, None)
    return {"ok": True, "destroyed": room}


def op_send(s, b):
    room, text = _require(b, "room", "text")
    r = _room(s, room)
    if b["agent"] not in r["members"]:
        raise Err(403, f"{b['agent']!r} is not a member of {room!r}")
    msg = s._append(room, b["agent"], text)
    return {"ok": True, "seq": msg["seq"]}


def op_dm(s, b):
    to, text = _require(b, "to", "text")
    s.touch(to)
    msg = s._append(s.dm_key(b["agent"], to), b["agent"], text)
    return {"ok": True, "seq": msg["seq"]}


def op_read(s, b):
    """Return room messages after `since` (default: the agent's cursor) and advance it.

    `room` is a room name or an explicit DM key (starts with '@'); both index
    `messages` directly, so no lookup branch is needed.
    """
    (room,) = _require(b, "room")
    default = s.cursors.get((b["agent"], room), 0)
    since = int(b["since"]) if b.get("since") not in (None, "") else default
    msgs = [m for m in s.messages.get(room, []) if m["seq"] > since]
    if msgs:
        s.cursors[(b["agent"], room)] = msgs[-1]["seq"]
    return {"room": room, "messages": msgs}


def op_inbox(s, b):
    """Peek unread across joined rooms + DMs without advancing cursors (read consumes)."""
    out = []
    for key in s.relevant_rooms(b["agent"]):
        unread = s.unread(b["agent"], key)
        if unread:
            out.append({"room": key, "unread": len(unread), "messages": unread})
    return {"inbox": out}


def op_invite(s, b):
    room, target = _require(b, "room", "target")
    r = _room(s, room)
    if b["agent"] not in r["members"]:
        raise Err(403, f"{b['agent']!r} is not a member of {room!r}")
    s.touch(target)
    r["members"].add(target)
    return {"ok": True, "room": room, "invited": target}


def op_kick(s, b):
    room, target = _require(b, "room", "target")
    r = _room(s, room)
    if r["owner"] != b["agent"]:
        raise Err(403, f"not owner of {room!r} (owner {r['owner']!r})")
    r["members"].discard(target)
    return {"ok": True, "room": room, "kicked": target}


OPS = {
    "register": op_register, "whoami": op_whoami, "agents": op_agents, "status": op_status,
    "create-room": op_create_room, "rooms": op_rooms, "join": op_join, "leave": op_leave,
    "destroy-room": op_destroy_room, "send": op_send, "dm": op_dm, "read": op_read,
    "inbox": op_inbox, "invite": op_invite, "kick": op_kick,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence default stderr access log
        pass

    def _reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {self.server.token}":
            return self._reply(401, {"error": "unauthorized"})
        action = self.path.strip("/")
        op = OPS.get(action)
        if not op:
            return self._reply(404, {"error": f"unknown action {action!r}"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._reply(400, {"error": "bad JSON body"})
        agent = body.get("agent")
        if not agent:
            return self._reply(400, {"error": "missing 'agent' (set COMMS_AGENT)"})
        try:
            with self.server.store.lock:
                self.server.store.touch(agent)
                result = op(self.server.store, body)
            return self._reply(200, result)
        except Err as e:
            return self._reply(e.code, {"error": e.msg})
        except Exception as e:  # last-resort guard so one bad request can't kill a thread silently
            return self._reply(500, {"error": f"{type(e).__name__}: {e}"})


def serve(token, port=0, host="0.0.0.0"):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.store = Store()
    httpd.token = token
    return httpd


def _demo():
    """In-process integration self-check: roundtrip + auth + owner-only destroy."""
    import urllib.request

    httpd = serve("demo-token", port=0, host="127.0.0.1")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(action, agent, token="demo-token", **fields):
        req = urllib.request.Request(
            f"{base}/{action}", data=json.dumps({"agent": agent, **fields}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    # auth
    assert call("rooms", "a", token="wrong")[0] == 401, "bad token must 401"
    # register + room + send + read roundtrip
    assert call("create-room", "alice", name="r")[1]["owner"] == "alice"
    assert call("join", "bob", room="r")[0] == 200
    assert call("send", "alice", room="r", text="hi")[1]["ok"]
    code, doc = call("read", "bob", room="r")
    assert code == 200 and [m["text"] for m in doc["messages"]] == ["hi"], doc
    # read advances the cursor: second read sees nothing new
    assert call("read", "bob", room="r")[1]["messages"] == []
    # inbox peek for a fresh reader
    assert call("send", "alice", room="r", text="again")[1]["ok"]
    assert not call("inbox", "carol")[1]["inbox"]  # not a member yet -> empty inbox
    assert call("join", "carol", room="r")[0] == 200
    assert call("inbox", "carol")[1]["inbox"][0]["unread"] == 2  # fresh joiner sees backlog
    # dm
    assert call("dm", "alice", to="bob", text="psst")[1]["ok"]
    assert call("inbox", "bob")[1]["inbox"], "bob should see a DM in inbox"
    # owner-only destroy
    assert call("destroy-room", "bob", room="r")[0] == 403, "non-owner destroy must 403"
    assert call("destroy-room", "alice", room="r")[1]["destroyed"] == "r"
    assert not any(x["name"] == "r" for x in call("rooms", "alice")[1]["rooms"])

    httpd.shutdown()
    print("demo ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.demo:
        return _demo()
    if not args.token:
        sys.exit("--token is required (or use --demo)")
    httpd = serve(args.token, port=args.port)
    # Announce the OS-assigned port on the first stdout line so the parent (spawn.py)
    # learns it race-free, then serve until killed.
    print(json.dumps({"port": httpd.server_address[1]}), flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
