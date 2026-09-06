STATUS: RUNNING

**Last updated:** 2026-09-06T14:10:00Z
**Summary:** Live capture started. SSE connected on both targets at 2026-09-06T14:07:17Z with the real MBTA API key — that timestamp is the start of the 7-day clock. Both `/predictions` streams are receiving real events (`reset`, then `add`/`update`/`remove`), and all three poll streams (`/schedules`, `/vehicles`, `/alerts`) are writing for both targets.

## Needs from human

- None blocking right now.
- **Ongoing:** note the date/approx time whenever a real commute goes badly, in `prototypes/BAD-COMMUTES.md`. Ground truth for S6, not reconstructable later.

## Activity log

- 2026-09-06T13:00 — Deployed keyless; REST polling live, SSE correctly 406-looping pending the key (see FINDINGS.md — confirmed via MBTA's own docs that this requires a key, not a recorder bug).
- 2026-09-06T13:0x — Orchestrator asked for exact specifics on an Accept-header experiment used during 406 debugging. Answered precisely: it was a one-off anonymous plain-JSON GET via content negotiation, not a streaming bypass, never present in `recorder.py` (grep-confirmed), never used for capture. Corrected the earlier loose phrasing in FINDINGS.md. Also itemized Proxmox provenance there: CTID 101 confirmed new, `ai-inference` (VM 100) confirmed untouched beyond two read-only listing commands, exact teardown command recorded.
- 2026-09-06T14:07 — User placed the key at `/Users/bradleybares/Git/commute-alert/prototypes/s1-transit-capture/.secrets/mbta.env` (main checkout). Copied into the worktree's gitignored `.secrets/` (this session runs in a worktree that doesn't share that directory with the main checkout) and re-ran `./deploy/deploy.sh`. **Confirmed**: both SSE connections went `connected` within ~200ms of the key reaching the container, both are receiving real events (sampled a live `reset` event on Red Line/Harvard with real `arrival_uncertainty`/`update_type` values). REST polling continues alongside.
- **7-day clock starts now** (first successful SSE connect, both targets: 2026-09-06T14:07:17Z), not from initial deployment. Done criterion: ≥7 consecutive days, ≥5 weekday morning + ≥5 weekday evening windows covered, gaps logged, at least one human-flagged bad commute inside the window (needs `BAD-COMMUTES.md` entries — currently empty).
- Not yet verified: a real reconnect under the key (to confirm `Last-Event-Id` resume behavior) — will show up naturally over the week; will check back periodically rather than force one.
