#!/usr/bin/env python3
"""Reconcile E4's heartbeat count and confirm what was actually on the wire.

Written to settle two challenges from the orchestrator: whether the run was 25
or 26 successful heartbeats, and whether the ISO-8601 `updatedAt` claim in F9
rests on observed payloads or only on reading the code.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
S2_HISTORY = pathlib.Path(
    "/Users/bradleybares/Git/commute-alert/.claude/worktrees"
    "/s2-apns-harness/prototypes/s2-apns-harness/logs/send-history.jsonl"
)

rows = [json.loads(l) for l in (ROOT / "data" / "e4-heartbeats.ndjson").open()]
ok = [r for r in rows if r.get("status") == 200]
dead = [r for r in rows if r.get("status") == 410]
print(f"heartbeats sent : {len(rows)}")
print(f"  200          : {len(ok)}")
print(f"  410          : {len(dead)}")
print(f"  last 200     : {ok[-1]['sent_at']}  ({ok[-1]['elapsed']})")
print(f"  first 410    : {dead[0]['sent_at']}  ({dead[0]['elapsed']})")

print("\n-- payload bodies recorded in S2's send-history.jsonl --")
e4 = [json.loads(l) for l in S2_HISTORY.open()
      if '"experiment": "E4"' in l]
iso, numeric, missing = [], [], []
for r in e4:
    cs = r["payload"]["aps"].get("content-state", {})
    v = cs.get("updatedAt")
    (iso if isinstance(v, str) else numeric if isinstance(v, (int, float)) else missing).append(v)
print(f"E4 sends with a recorded body : {len(e4)}")
print(f"  updatedAt as ISO-8601 string: {len(iso)}")
print(f"  updatedAt as number         : {len(numeric)}")
print(f"  updatedAt absent            : {len(missing)}")
if iso:
    print(f"  example                     : {iso[0]!r}")
