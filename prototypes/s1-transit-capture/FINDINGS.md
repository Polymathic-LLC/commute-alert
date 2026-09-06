# S1 Findings — MBTA stream recorder

Step 0 (archive hunt) is owned by a parallel session (`prototypes/s1a-archive-hunt/`) and is
not duplicated here. Its result, relayed to this session: **no public archive contains
prediction-level records** — every candidate was observed events or pre-aggregated accuracy
counts, and MBTA discards the prediction stream after deriving those. Live capture is the
only source. That finding raises the cost of a wrong capture configuration, since a week
run against the wrong shape can't be redone.

---

## Streaming requires an API key — anonymous SSE returns 406

**Question.** Does the documented SSE approach (`Accept: text/event-stream`) work as described?

**Evidence.** A local dry run against the live MBTA API with no key returned `406
Not Acceptable` (`{"errors":[{"code":"not_acceptable","status":"406"}]}`) on every SSE
connection attempt to `/predictions`, on both targets. Plain REST polling (`/schedules`,
`/vehicles`, `/alerts`) with the same unauthenticated client succeeded (`200 OK`) on every
call. Confirmed against MBTA's own streaming docs (mbta.com/developers/v3-api/streaming):
*"Anonymous access is not possible for streaming."* An API key is mandatory for SSE,
via `x-api-key` header or `api_key` query param; REST endpoints work anonymously at a
lower rate limit.

**Answer.** This is expected behavior, not a bug in the recorder — the Accept header and
`x-api-key` handling in `recorder.py` already match MBTA's own example curl command
verbatim. The 406s go away the moment a real key is supplied. Recorded here mainly so the
406 seen in a keyless dry run is never mistaken for a code defect.

**Confidence.** High — reproduced directly, confirmed against primary-source docs.

---

## SSE event types: four, not three — `add` is undocumented in `docs/mbta-api.md`

**Question.** What SSE event types does the stream actually send?

**Evidence.** MBTA's streaming docs list four: `reset`, `add`, `update`, `remove`.
`docs/mbta-api.md` (as read from the main checkout at session start) lists only three:
`reset`, `update`, `remove` — `add` is missing.

**Answer.** `recorder.py`'s SSE parser does not special-case event types (it stores
whatever `event:` value arrives verbatim), so this doesn't require a code change. It does
mean an `add` event is not a corruption or a code bug if seen in the capture. Doc
correction owned by the orchestrator, not this session.

**Confidence.** High — directly quoted from MBTA's own docs page via WebFetch.

---

## Field-shape corrections relayed from S1a (not this session's own observation)

The orchestrator relayed these from S1a's cross-check against a raw `TripUpdates_enhanced.json`
snapshot and live V3 sampling. Noting provenance explicitly per the orchestrator's request —
these are S1a's findings, not independently derived here, except where marked "independently
confirmed" below (this session's own curl sampling of the live Red Line SSE stream happened
to hit the same fields and corroborates them).

- **`arrival_uncertainty`/`departure_uncertainty` are a coded enum, not a raw seconds value.**
  Rail: `60` = trip started, `120` = terminal/reverse awaiting departure, `360` =
  terminal/reverse while still finishing a previous trip. **Independently confirmed**: this
  session's own live curl sample of the Red Line stream returned `arrival_uncertainty: 60`
  and `arrival_uncertainty: 120` on real in-service predictions, consistent with the enum.
  `docs/mbta-api.md`'s framing ("confidence level in seconds... >300s means low-confidence")
  is misleading if taken literally as continuous seconds. `recorder.py` does not bucket or
  threshold this value at capture time — it is written to NDJSON exactly as MBTA sends it,
  so this doesn't require a recorder change, only a downstream (S6) awareness.
- **`update_type` is UPPERCASE in practice** (`MID_TRIP`, `AT_TERMINAL`), plus a third value
  **`REVERSE_TRIP`** that `docs/mbta-api.md` doesn't mention at all. **Independently
  confirmed**: this session's own curl sample of the Red Line stream returned
  `"update_type":"MID_TRIP"` and `"AT_TERMINAL"` — uppercase, matching S1a. `recorder.py`
  never compares against a hardcoded case, so no code bug results, but any future code
  (S6, or the real backend) that copies the lowercase example from the doc into a
  case-sensitive comparison would silently never match.
- **`update_type` and `status` are enhanced-JSON-only, undocumented/experimental fields** —
  absent from the standard GTFS-RT protobuf feed. Per S1a: on commuter rail specifically,
  `update_type`, `arrival_uncertainty`, and `schedule_relationship` were `null` in 111/111
  sampled live V3 predictions (two samples, 45 minutes apart, Sunday only — S1a rates this
  medium confidence pending a weekday sample). Their absence is not an error condition and
  `recorder.py` does not treat it as one — it records `null` faithfully.
- **The doc field is `status_text`; the real field is `status`.** Doc fix owned by the
  orchestrator.

## Capture fidelity decision: Red Line at Harvard gets equal fidelity, not a thinner sample

The orchestrator raised this as a decision, not a question: if S1a's commuter-rail-nulls
finding holds, Red Line/`place-harsq` may be the *only* place `update_type` and
`arrival_uncertainty` are observable at all, since they're consistently null on commuter
rail. Recorded here for traceability: **no code change was needed**. `recorder.py` never
gave the secondary target a thinner capture — both targets share the same poll intervals
(`VEHICLES_POLL_INTERVAL_S`, `SCHEDULES_POLL_INTERVAL_S`, `ALERTS_POLL_INTERVAL_S`) and both
run a full, unfiltered SSE `/predictions` subscription. This was already true before the
orchestrator's message; confirmed by re-reading `recorder.py`'s `run()` function, which
builds the same four tasks (predictions SSE + 3 pollers) per target from one shared
`TARGETS` list.

---

## Secondary target selection: Red Line at Harvard (`place-harsq`)

**Question.** Which rapid-transit stop for the secondary capture target?

**Answer.** Red Line, Harvard Square (`place-harsq`). Chosen over a terminus (e.g. Alewife)
because a terminus stop would show `AT_TERMINAL` for essentially every prediction and never
exercise the mid-trip staleness signal the secondary target exists to test. Harvard is a
high-frequency, non-terminus, both-directions-in-one-parent-stop location. This became more
load-bearing than originally framed once S1a's commuter-rail-nulls finding came in — see
above.

**Confidence.** High for "a reasonable choice"; not compared quantitatively against other
mid-line Red Line stops (e.g. Porter, Davis) — any of those would likely have served
equally well. Not re-litigated given time cost of switching now.

---

## Deployment target

Created a dedicated LXC container on the `homelab` Proxmox node (the same physical node
that hosts `ai-inference` — no other Proxmox node was reachable from the network this
session ran on; `pve1`/192.168.1.100 timed out). Per DERISKING.md rules, `ai-inference`
(VM 100) was not touched — read-only inspection only (`qm list`, `pvesm status`) before
creating a wholly separate LXC.

- **CTID 101**, hostname `commute-alert-s1-recorder`, Debian 12, unprivileged, 1 vCPU,
  512MB RAM, 8GB disk, DHCP on `vmbr0`. Got `192.168.1.69`.
- SSH access installed (same key as the `homelab` host entry) and registered in
  `~/.ssh/config` as `Host commute-alert-s1`, so the human/orchestrator can reach it
  directly without going through the Proxmox host.
- Python 3.11 + venv + git installed. Deployment mechanism: `systemd` service running
  `recorder.py` directly (no Docker) — an unprivileged LXC doesn't need Docker-in-container
  nesting complexity for a single asyncio process; `systemd`'s `Restart=always` is the
  keep-alive. See `deploy/` in this directory.
- Torn down would mean: `ssh homelab 'pct stop 101 && pct destroy 101'`.

---

## Open / not yet answered

- **Actual 7-day capture has not started** — blocked on the MBTA API key (STATUS.md).
  Recorder is deployed and ready; the systemd unit is installed but not yet enabled, pending
  the key landing in `.secrets/mbta.env` so it isn't started keyless and then need a restart
  mid-stream (a restart is fine and gets logged as a gap, but there's no reason to burn a
  gap on something avoidable).
- **Whether `Last-Event-Id`-based resume actually works on reconnect** — implemented per
  MBTA's documented support for it, but not yet verified against a real reconnect under
  load (needs the key + a live multi-hour run).
- Every question under "Questions to answer" in DERISKING.md's S1 section (concurrent
  prediction counts, trip_id reconciliation, no-prediction-for-scheduled-trip rate, vehicle
  staleness distribution, `AT_TERMINAL` correspondence to reality, SSE connection
  durability) is unanswered until the capture runs — that's S6's job once ≥7 days exist.
