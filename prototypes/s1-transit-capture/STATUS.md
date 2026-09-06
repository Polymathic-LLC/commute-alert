STATUS: BLOCKED

**Last updated:** 2026-09-06T13:00:00Z
**Summary:** Recorder is deployed and running on its own Proxmox container (`homelab` node, CTID 101, `192.168.1.69`), capturing REST-poll data (schedules/vehicles/alerts) for both targets right now. The one remaining blocker is the MBTA API key — SSE prediction capture (the primary artifact) 406s without one, confirmed against MBTA's own docs ("anonymous access is not possible for streaming"), and reconnects harmlessly in a backoff loop until a key arrives.

## Needs from human

1. **MBTA V3 API key.** Drop it at:
   `/Users/bradleybares/Git/commute-alert/prototypes/s1-transit-capture/.secrets/mbta.env`
   containing one line: `MBTA_API_KEY=<your key>`
   That path is gitignored (root `.gitignore` excludes `prototypes/**/.secrets/`). Once it's there, re-running `./deploy/deploy.sh` picks it up, pushes it to the container, and restarts the service — SSE capture starts immediately.
2. ~~Proxmox access~~ — **resolved.** Existing SSH access (`~/.ssh/config` `homelab` entry) was sufficient; no new credentials needed. Container is up and reachable directly at `ssh commute-alert-s1`.
3. **Ongoing, once SSE capture is live:** note the date/approx time whenever a real commute goes badly, in `prototypes/BAD-COMMUTES.md` (owned by the orchestrator, not this session — just noting it here since it's the human-facing ask). Ground truth for S6, not reconstructable later.

## Activity log

- Skipped step 0 (archive hunt) per orchestrator scope note — owned by parallel session `prototypes/s1a-archive-hunt/`. Relayed result: no usable prediction-level archive exists anywhere; live capture is the only source (see FINDINGS.md).
- Wrote `recorder.py`: asyncio recorder, SSE predictions + periodic schedules/vehicles/alerts polling per target, NDJSON output, exponential-backoff reconnect with an explicit connection/gap log, internal per-task crash supervision.
- Chose secondary rapid-transit target: Red Line at Harvard (`place-harsq`) — see FINDINGS.md for rationale, which got stronger once S1a reported several unhappy-path fields are null on commuter rail.
- Confirmed via local dry run + live curl probing: the 406 seen without an API key is expected (MBTA requires a key for streaming, not just REST), not a code bug. Also independently confirmed two of S1a's field-shape findings (`update_type` uppercase, `arrival_uncertainty` as a coded enum) against live data. Full detail in FINDINGS.md.
- Created a dedicated Proxmox LXC (CTID 101, `commute-alert-s1-recorder`, on the `homelab` node — did not touch `ai-inference`, VM 100, read-only inspected it only to confirm it was a VM not an LXC).
- Deployed via `systemd` (`deploy/commute-alert-s1.service`, `Restart=always`) — no Docker; a single asyncio process doesn't need container nesting. `deploy/deploy.sh` is idempotent, rsyncs code + `.secrets/mbta.env` if present, and restarts the service.
- Verified live: REST polling (schedules/vehicles/alerts) writes real NDJSON data for both targets right now; SSE correctly 406s and backs off (1s→2s→4s...capped at 60s) without crashing.
- Not yet done: SSE capture (blocked on key), the 7-day clock (hasn't started — starts once SSE is live, since that's the primary artifact), `Last-Event-Id` resume verification under a real reconnect.
