# S4 — measurement protocol

Every experiment below states: the **claim** under test, the **protocol**, the **sample
size**, the **device-side observation** that makes it a measurement, and **what would
falsify it**. An experiment without a device-side observation is not run.

## The governing constraint

S2's first push-to-start returned `200 OK` from APNs and started nothing on the device —
the payload used snake_case keys that ActivityKit's decoder rejects. APNs validates that
the body is JSON; it never checks the body against your `ContentState`.

**A 200 from APNs is not evidence that a Live Activity did anything.** A throughput ramp
that counts 200s would produce a confident, precise, completely wrong number. So:

> No experiment here reports a landing result derived from APNs status codes alone.
> Every landing claim is backed by an on-device record.

The one legitimate use of APNs responses is the *negative* direction: a `410 Unregistered`
or `403 ExpiredToken` is authoritative evidence that the activity is **gone**, because that
is a fact APNs itself holds. That is used in E4 and nowhere else.

## Device under test — and the version caveat that qualifies every number here

| | |
|---|---|
| Model | iPhone 15 Pro (`iPhone16,1`) |
| iOS | **26.5** |
| App | `com.polymathic.commutealert.s3probe`, built against iOS 26.2 SDK, deployment target 17.2 |
| Paired Watch | none currently — the user has one and is willing to pair it, so E7 is schedulable, not unmeasurable |
| APNs env | sandbox (`aps-environment: development`) |

`ios/CLAUDE.md` and the plan target **iOS 17.2+**, because 17.2 is the push-to-start floor.
Every measurement here comes from **iOS 26.5 — nine major versions past that floor.** Live
Activity budget, throttling, push-to-start reliability and the 8-hour cap are precisely the
kind of platform behaviour Apple changes quietly between releases.

So every finding is written as "on iOS 26.5, X", never as "X". Whether the product can
actually support its stated 17.2 floor is a real open question for layer 2, not something
this workstream may quietly assume away.

**`Info.plist` sets `NSSupportsLiveActivitiesFrequentUpdates = true`.** Every budget number
S4 produces is therefore the *frequent-updates* ceiling on a device where the user has not
turned that off. This is not a footnote — it is the single most important qualifier on E2,
and it is a product decision the design must make explicitly. The default (key absent)
ceiling is **not** measured here unless a second build is made; see "Not measured".

## Budget already consumed against this device

From S2, before S4 took over (subtract from any baseline):

| When (EDT) | Type | Effect |
|---|---|---|
| 2026-09-06 16:40:04 | alert | banner shown |
| 2026-09-06 16:40:14 | background | app woke |
| 2026-09-06 16:40:14 | la-start (push-to-start) | **decoded to nothing** — bad keys |

Whether a push whose payload fails to decode still draws from the update budget is itself
unknown. E2 does not depend on the answer (its ramp is measured against its own baseline),
but the question is recorded in FINDINGS as open.

---

# Instruments

Three independent device-side observers, in decreasing order of coverage and increasing
order of trustworthiness. Findings say which observer produced each number.

### I1 — widget render log (unattended, primary)

`CommuteLiveActivity`'s view body runs in the **widget extension process** every time the
system renders the Live Activity. A call from that body appends one NDJSON line to the
shared App Group container recording the wall-clock time and the content state it was
handed. This is what converts "a human stares at a lock screen for two hours" into an
unattended record of which pushes actually landed.

**I1 is not trusted until E0 calibrates it.** A render is not the same event as an update:
iOS may coalesce renders, may not render at all while the screen is off, and may re-render
without a content change. I1 therefore yields, per update, *evidence of arrival*, while its
absence is weak evidence of non-arrival until the capture rate is known.

### I2 — in-app `contentUpdates` (attended, exact)

While the app process is alive, `for await content in activity.contentUpdates` yields every
content state ActivityKit applies, with a precise local timestamp. This is ground truth for
"iOS applied this update", but only while the app runs. Used to calibrate I1 (E0a) and for
short attended experiments.

I2 is deliberately **not** used for the budget ramp: keeping the app alive to observe would
change the thing being measured.

### I3 — `Activity.activities` snapshot (any time, coarse)

On every launch and on demand, the app enumerates live activities — id, `activityState`,
current content state, `pushToken`. One reading tells you *what survived*, not *what
happened*. It is the reconciliation instrument (E8) and the tiebreaker when I1 is ambiguous.

### Transport

All three write NDJSON to the App Group container
`group.com.polymathic.commutealert.s3probe`, appended with POSIX `O_APPEND` so the widget and
app processes cannot interleave a line.

Getting it off the phone is deliberately low-tech. An earlier design had an HTTP collector on
the Mac, an ATS local-networking exception and a live upload panel; **all of it existed only
to avoid asking a human, and all of it was cut** once the user said they would rather be
asked. What replaced it: `UIFileSharingEnabled`, so the log appears in the Files app and can
be AirDropped in one gesture, plus an on-device summary screen that groups observed renders by
experiment tag and lists the sequence numbers seen — so the common case needs no file transfer
at all, just a screenshot.

### Correlation key

Every push carries its experiment id in fields the device echoes back:
`attributes.routeName = "<experiment>"` (push-to-start only, since attributes are immutable
once the activity exists) and `content-state.headline = "S4 <exp> <seq> <nonce>"`. `seq` is
a zero-padded integer increasing monotonically within an experiment. The device log records
the headline verbatim, so `sent seq` ∩ `observed seq` is computable without trusting any
clock but our own.

---

# E0 — instrument calibration

**Claim.** I1 (widget render log) records every content-state update iOS applies, under the
conditions the later experiments run in.

**Why it comes first.** Every drop count in E2 is `sent − observed`. If I1 silently
undercounts, E2 reports a throttle that is really an instrument artifact. That is the same
class of error as counting 200s, one layer down.

### E0a — capture rate against an exact observer (attended, ~5 min)

App **foregrounded**, activity live. Send 5 updates at 30 s spacing. Compare I2 (exact)
against I1 (renders).

- I2 sees 5 of 5 → ActivityKit applies updates at 30 s spacing (2/min). Also a first, cheap
  data point against the "~4/hour" figure.
- I1 sees 5 of 5 → I1 is exact under this condition.
- I1 sees fewer → record the ratio. Renders may simply not happen while the Live Activity is
  not on screen, in which case E0a proves nothing about the locked case and E0b decides.

**Falsifier.** I2 < 5 means updates are being dropped at 2/min even in the friendliest
condition, and the whole budget picture is worse than Apple documents. That is a finding,
not a setback.

### E0b — capture rate in the measurement condition (unattended, 1 h)

Phone **locked**, face down, untouched, app not foregrounded. Send 4 updates at 15-minute
spacing — **4/hour, exactly Apple's documented budget**, chosen so that throttling is not a
plausible explanation for a miss.

- I1 records 4 of 4 → I1 is trusted at 1.0 for locked/unattended runs; E2's drop counts are
  real drops.
- I1 records fewer → I1's capture rate is `k/4` and **every E2 landing count is a lower
  bound only**. Findings will say so, and E2's conclusions will be restricted to the
  *relative* shape of the ramp (where landings fall off) rather than to absolute counts.

**Falsifier of the whole instrument.** 0 of 4. Then I1 is unusable, E2 needs a redesign
around periodic human reads, and I say so rather than shipping a number.

---

# E1 — push-to-start reliability

**The question the product rests on.** `docs/architecture.md` decision 3 makes Live
Activities the primary real-time surface and assumes the backend can start one with no user
interaction. If push-to-start does not fire after a force-quit, that assumption is false and
the design changes.

**Claim.** A push-to-start push starts a Live Activity regardless of the app's process
state, boot state, or power mode.

### Conditions

| # | Condition | Trials | Why |
|---|---|---|---|
| C1 | App backgrounded normally (home swipe), phone locked | 2 | baseline; isolates the instrument |
| C2 | App **force-quit** from the app switcher, ≥2 min settle | 3 | the assumption most likely to be false |
| C3 | **Reboot, never unlocked** (before-first-unlock) | 1 | data-protection classes may block ActivityKit |
| C4 | **Reboot, unlocked once, app never launched** | 2 | "has never been foregrounded this boot" |
| C5 | **Low Power Mode** on + force-quit | 2 | LPM defers background work |

10 trials. n=3 on the headline condition can establish *works* or *fails*; it cannot
distinguish 95 % from 100 %. Findings state the trial count next to every claim and do not
use the word "reliable" for n=3.

### Protocol (clock-driven, so the human never waits on me)

Each trial is a fixed 4-minute slot on a wall clock the human and I share:

```
T+0:00  human performs the condition's action, then locks the phone and puts it down
T+1:30  S4 sends push-to-start   (attributes.routeName = "S4-E1-<cond>-t<n>")
T+3:00  human raises the phone, reads the lock screen, writes one line, does not unlock
T+4:00  next trial
```

Reboots (C3, C4) get an 8-minute slot. Between trials S4 sends `la-end` with a
`dismissal-date` in the past to clear the previous card, so a stale card is never mistaken
for a new one — and each trial's `routeName` is unique, so even a missed end is detectable.

### Observation

1. **Human, per trial** — one row: `time | condition | card present y/n | routeName on card`.
2. **I1**, unattended — a render line whose `routeName` matches the trial. Force-quitting the
   app does **not** kill the widget extension, so I1 should survive C2; the C1-vs-C2
   comparison in I1 validates that assumption rather than assuming it.
3. **I3**, at the end — the app enumerates surviving activities.

Three observers, so a disagreement is visible rather than silent.

**Falsifier.** Any trial where the human sees no card *and* I1 has no matching render *and*
I3 shows no activity = push-to-start failed for that condition. One failure in C2 is enough
to demote push-to-start from "assumed" to "must be handled", and that is reported as the
headline finding regardless of how the other nine trials went.

### Free riders

The app logs the push-to-start token at every launch. If it differs before and after the C3
reboot, **the token rotates across reboot** and the backend must handle rotation — an
`Open` item in `push-flow.md` answered at zero extra cost.

---

# E2 — update budget

**Claim.** There is a ceiling on Live Activity update delivery, it is discoverable, and it
behaves as a rate limit that recovers rather than a hard cap that kills the activity.

**Confound named up front.** This build sets `NSSupportsLiveActivitiesFrequentUpdates`. The
number produced is the frequent-updates ceiling. Apple's ~4/hour guidance describes the
*default* ceiling. These are different quantities and findings will not conflate them.

### Design: descending-interval blocks with a recovery probe

One activity, phone locked and untouched. Each block holds a fixed send interval; after each
block, **5 minutes of silence, then a single distinctively-marked recovery probe**.

| Block | Interval | Sends | Duration | Nominal rate |
|---|---|---|---|---|
| B1 | 300 s | 6 | 30 min | 12/h |
| B2 | 120 s | 10 | 20 min | 30/h |
| B3 | 60 s | 15 | 15 min | 60/h |
| B4 | 30 s | 20 | 10 min | 120/h |
| B5 | 10 s | 30 | 5 min | 360/h |
| B6 | 2 s | 60 | 2 min | burst |

141 sends, ~82 min plus 30 min of recovery gaps ≈ 2 h unattended, zero human attention.

**The recovery probe is the load-bearing part.** It distinguishes:

- probe lands → the limiter is a **rate limit that recovers**; the ceiling is a throughput
  number and a backend can pace against it.
- probe does not land, but a later block's sends do → **soft/temporary suppression**.
- probe does not land and nothing lands again → the activity was **killed** by exceeding the
  budget, which is a far more serious design constraint than a dropped update.

### Priority

B3 is run twice: once at `apns-priority: 10`, once at `5`. Apple describes priority-5 Live
Activity updates as budget-friendly and deferrable. If the priority-5 pass lands a higher
fraction, priority is a lever the backend should use for routine updates while reserving 10
for genuine status changes — a direct input to `push-flow.md`.

### Per-activity or per-app?

A **second** activity (`S4-E2B`) is started before B1 and receives one update every 10
minutes throughout, marked distinctly. If E2B's updates keep landing while E2A is being
throttled, the budget is **per-activity**; if they stop in step, it is **per-app**. The
product's shape depends on this (one activity per user vs. one per watched route) and no one
has asked the question.

### Observation

I1 only, calibrated by E0b, plus a single human reading of the final card and one
screenshot. Landing counts are reported as `observed/sent` per block **with I1's calibrated
capture rate stated alongside**. If E0b showed capture < 1.0, the absolute numbers are
reported as lower bounds and the conclusion is restricted to the ramp's shape.

**Falsifier of the "there is a usable ceiling" claim.** Landings fall off with no stable
plateau, or the recovery probes never land — in which case the finding is "the budget is not
a rate the backend can pace against", which would change the design more than any number.

---

# E3 — `apns-collapse-id`

**Claim.** Under rapid successive updates sharing a collapse-id, only the last is presented;
distinct collapse-ids present independently.

Three arms, one activity, phone locked:

- **A3.1 fast/shared** — 5 updates, 1 s apart, identical `apns-collapse-id: s4-e3`.
- **A3.2 fast/distinct** — 5 updates, 1 s apart, distinct collapse-ids.
- **A3.3 slow/shared** — 3 updates, 20 s apart, identical collapse-id. **This arm carries the
  result**: 20 s spacing is far below any plausible throttle, so if only the last of the
  three renders, collapsing is real and is not throttling wearing a disguise.

Confound acknowledged: at 1 s spacing, A3.1 and A3.2 cannot separate collapsing from rate
limiting. They are run for the comparison between them, not for an absolute claim. A3.3 is
the clean measurement.

Plus one send with a **65-byte collapse-id**, expecting `400 BadCollapseId` — closes an open
row in S2's failure-mode table for the cost of one push. (This one *is* an APNs-response
finding, legitimately: the claim is about what APNs rejects, not about what the device does.)

---

# E4 — the 8-hour cap

**Claim.** A Live Activity is terminated by the system at a fixed age, and the backend can
learn about it from APNs rather than from the device.

**Protocol.** Start an activity at a recorded time. Send a heartbeat update carrying elapsed
minutes in the headline every **30 minutes**, tightening to every **5 minutes** across the
7 h 30 m – 8 h 30 m window, and continue past 8 h until the token is definitively dead or
12 h elapses.

**Observation.** Unusually, this one has a rigorous unattended observer that is *not* I1:
the APNs response itself. The transition is **bracketed by the last heartbeat that returned
200 and the first that returned `410 Unregistered` / `403 ExpiredToken`** — a token going
dead is a fact APNs holds. 5-minute heartbeats near the cap give ±5 min resolution. I1 gives
the rendering side of the story, and one human check the next morning gives the user-visible
side: is the card still on the lock screen, has it moved, what does it say.

**This experiment needs no instrumented build and no human until morning**, so it starts
first, tonight, on whatever activity is currently alive.

**Falsifier.** If the token never dies and updates keep landing past 12 h, there is no cap on
this OS and `push-flow.md`'s lifecycle assumptions are wrong in the opposite direction.

**Sub-question that matters more than the cap itself.** Is the *user-visible* end (card
leaves the Lock Screen) simultaneous with the *token* death? If the card disappears while
updates still return 200, a backend can be pushing to an activity no one can see — exactly
the failure the product must not have, and the justification for a reconciliation design.

---

# E5 — concurrency

**Claim.** The per-app cap is 5 simultaneous Live Activities and the 6th fails predictably.

Start activities 1…6 via the app (local start, so failures surface as thrown errors with
messages rather than as silence), logging each result. Then attempt a **7th via
push-to-start** while 5 are live, to learn whether the push path fails the way the local path
does — the local path can report an error to the app; the push path cannot report anything to
anyone, and a silent failure there is a real operational hazard.

Observation: I3 enumerates what actually exists; the thrown error text for the local 6th; I1
for whether the pushed 7th ever rendered. Human confirms how many cards the lock screen
actually shows, which is not necessarily the number of live activities.

---

# E6 — ending

**Claim.** A backend `end` push and an in-app `end` produce the same user-visible outcome,
and `dismissal-date` controls how long the ended card lingers.

Four arms, each on its own activity, each observed by the human at +0 s, +2 min, +20 min:

| Arm | How ended |
|---|---|
| A | in-app `end(dismissalPolicy: .immediate)` |
| B | in-app `end(dismissalPolicy: .default)` |
| C | `la-end` push, `dismissal-date` in the **past** |
| D | `la-end` push, `dismissal-date` = **+15 min** |

The question that matters for the product: after an `end` push, is the card gone at once, or
does it sit on the lock screen showing a final state? "Your train left" lingering for fifteen
minutes is a feature; "monitoring stopped" lingering is clutter. This decides which.

---

# E7 — Watch mirroring

**Blocked on one fact:** is there a paired Apple Watch? If yes, E1's C1 trial and E2's B1
block are observed on the Watch as well as the phone, at no extra send cost. If no, this is
recorded as **unmeasured, because no paired Watch was available**, and `ios/CLAUDE.md`'s
mirroring assumption stays explicitly unverified rather than quietly assumed.

---

# E8 — restart reconciliation

**Claim.** A backend that has lost all in-memory state can keep pushing to an activity it did
not start, using only a stored token.

Protocol: take a per-activity token captured hours earlier, from a *different* process, with
no `Activity` handle anywhere — push an update to it and see whether it lands. That is
precisely the "backend restarted" situation. It runs for free as a side effect of E4, whose
every heartbeat is exactly this operation from a fresh process.

Second half, the one that actually bites: **can the backend discover that a stored token is
dead?** E4's bracketing answers it. If a dead activity's token returns `410 Unregistered`,
reconciliation is a matter of handling that response and `operations.md` can specify it. If
it returns 200 forever, the backend cannot tell, and the design needs a device-side heartbeat
instead. Those two outcomes imply very different systems.

---

# E9 — widget background-push budget

Lightest-weight check, run last and only if time allows. Background pushes at 15-minute
intervals for 2 hours; the app's `didReceiveRemoteNotification` logs each arrival to the same
NDJSON. `observed/sent` is the answer. Explicitly a rough measurement, and labelled as one.

---

# Not measured — stated so the next layer does not assume otherwise

- **iOS 17.2 through 25.x behaviour.** One device, iOS 26.5. Everything here is a measurement
  of current-OS behaviour and must not be read as holding at the 17.2 deployment floor.
- **The default (non-frequent-updates) budget.** Requires a second build with
  `NSSupportsLiveActivitiesFrequentUpdates` removed and a reinstall. Recorded as a known gap
  unless time allows a second pass.
- **Whether a push whose payload fails to decode still draws budget.** Isolating it needs a
  clean budget baseline, which conflicts with using the same device for E2.
- **Production APNs environment.** Sandbox only.
- **Device diversity.** One device, one carrier, one network. Nothing here separates
  device-specific from platform-wide behaviour.

---

# E10 — is the loading overlay iOS's staleness affordance?

Added after the human observed a Live Activity rendering correct content *with* a
progress/loading overlay on top (F7).

**Claim.** The overlay is iOS signalling "this content may be out of date", not an error.

**Why it is worth a designed test rather than a shrug.** If the platform degrades a card's
appearance on its own when updates stop, it provides a freshness signal for free, the cost of
a missed update drops, and the honest-freshness problem in `push-flow.md` has a partial
platform-provided answer instead of needing an app-side one. That is a design input, and it
points the opposite way from "a stale card silently lies to the user".

**Established already:** the probe passes `staleDate: nil` on local start and no push payload
sets `aps.stale-date`. So the overlay is *not* caused by a stale date we set.

**Protocol.** Start an activity with an explicit `staleDate` of now + 120 s (the app has a
button). Observe at +30 s (expect: no overlay) and +180 s (expect: overlay). Then start a
second with `staleDate: nil` and leave it untouched for an hour, checking once, to see whether
an overlay appears anyway — which would mean iOS applies a default staleness window.

**Falsifier.** The overlay appears at +30 s on the explicit-stale activity, or never appears
after the stale date passes. Either kills the staleness reading and the overlay means
something else.

**Sample size.** 2 activities, 3 observations. Cheap, and it rides along with any other
attended session.

---

# E7 — Watch mirroring

Moved from "unmeasured, because no hardware" to schedulable: the user has an Apple Watch, is
willing to pair it, and it is not currently paired.

**Claim.** `ios/CLAUDE.md` assumes Live Activities mirror to a paired Apple Watch. Does that
hold on this OS pair, and what does the mirrored presentation actually show?

**Cost, stated honestly.** Pairing a Watch is heavy device interaction — tens of minutes, and
it changes the device's state for everything afterwards. It is queued behind the questions that
block design decisions, per the user's own stated preference for fewer well-instrumented
measurements over broad coverage. Mirroring blocks nothing; the epoch question and the
push-to-start conditions do.

**Protocol, once paired.** No extra sends: E1's C1 trial and one E2 block are simply observed
on the Watch as well as the phone.
1. With an activity live, is it present on the Watch face / in the Smart Stack? Photograph it.
2. Push one update. Does the Watch presentation change, and roughly how long after the phone?
3. End the activity by push. Does the Watch card clear too, or linger?
4. With the phone powered off or out of range, does the Watch still show the activity?

**Falsifier.** No mirrored presentation appears with a paired, unlocked Watch and a live
activity on the phone. That would contradict `ios/CLAUDE.md` directly.

**If it stays unpaired:** recorded as **unmeasured, because the Watch was never paired within
the workstream's window** — not as "assumed to work".
