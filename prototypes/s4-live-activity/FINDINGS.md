# S4 — Findings

Answers as they are established. Each states the question, the evidence, the answer, and
confidence. A question that turns out to be unanswerable is itself a finding.

> ## Read this before quoting any number below
>
> **Every measurement here was taken on iOS 26.5** (iPhone 15 Pro, `iPhone16,1`), against the
> APNs **sandbox**, on a build whose `Info.plist` sets
> `NSSupportsLiveActivitiesFrequentUpdates = true`.
>
> The plan and `ios/CLAUDE.md` target **iOS 17.2+**, because 17.2 is the push-to-start floor.
> That is nine major versions below the device measured. Live Activity budget, throttling,
> push-to-start reliability and the 8-hour cap are exactly the platform behaviours Apple
> changes quietly between releases. So every finding below is written "on iOS 26.5, X" and
> **none of it may be generalised to the 17.2 deployment floor.** Whether the product can
> actually support 17.2 is a genuine open question for layer 2 — flagged here so it is a
> question somebody decided to leave open, rather than an assumption nobody noticed making.
>
> **A 200 from APNs is not evidence that a Live Activity did anything.** No landing claim
> below rests on an APNs status code. See F2, which is the empirical demonstration.

---

## F1 — The push-to-start payload fix is confirmed at the APNs layer only. Device side pending.

**Question.** S2's first push-to-start returned 200 and started nothing, because the payload
used snake_case keys that ActivityKit's decoder rejects. Does the corrected payload actually
start a Live Activity?

**Evidence so far.** At 16:57:09 EDT S2 sent `la-start` to the push-to-start token with
`attributes {routeName: "S4-A1", stopName: "Boston Landing"}` and a `content-state` matching
S3's struct exactly. APNs returned `200`, `apns-id e32ed27b-…`,
`apns-unique-id 98e5fad1-…`.

**Answer: NO — resolved negative at 17:06 EDT. Superseded by F6, which carries the detail.**
The human's Lock Screen showed one card and it was the locally-started one. No `S4-A1` card
ever appeared. The snake_case fix was necessary but not sufficient.

**Confidence: high** — direct human observation, and the `routeName` correlation key made the
reading unambiguous rather than a judgement call.

---

## F2 — APNs gives a sender no signal that a Live Activity is unhealthy. (Provisional, and it is the most consequential thing measured today.)

**Question.** Can a backend tell, from APNs responses alone, whether its Live Activity updates
are reaching the device?

**Evidence.** Four pushes now known to have produced no Live Activity, every one a `200 OK`:

| Push | Known defect | APNs said |
|---|---|---|
| 16:40:14 `la-start` | payload keys the device cannot decode | `200` |
| 16:57:09 `la-start` | struct-matching keys, still started nothing (F6) | `200` |
| 17:11:53 `la-start` | `S4-B1-iso`, ISO-8601 `Date` the decoder rejects (F6) | `200` |

And in the same batch, two pushes that *did* produce cards (`S4-B2`, `S4-B3`) returned the
identical `200`. So APNs gave the same response to three pushes of which one silently produced
nothing and two worked. The response carries no information about the outcome in either
direction.

APNs validates that the body is JSON and that the token is well-formed for the topic. It never
compares the body against the app's `ContentState`.

**Correction to an earlier draft of this finding.** It previously cited the 16:57:10
`la-update` as a 200 sent "to a token whose activity was dead". That was wrong, and it was
wrong in the direction that would have made this finding look stronger than the evidence
supports. The human's 17:06 observation established that the locally-started activity was
**alive** at the time, so that 200 was simply correct and is not evidence of anything. Whether
APNs ever reports a *genuinely* dead activity is still untested — it is what E4/F5 is for.

**Answer (provisional): no.** A backend that infers delivery from status codes will report
perfect health while shipping nothing to the device.

**Design consequence if this holds.** The backend cannot close the loop on its own pushes.
Either the device reports back (an app-side receipt), or the system is designed to tolerate
never knowing. This lands squarely on `operations.md` restart reconciliation and on the
`live_activities` open item in `data-model.md`.

**Confidence: high for the claim as stated** — that a `200` does not distinguish a push that
rendered from one the device silently discarded. Three pushes in one batch, one variable
between them, two outcomes, one response code. That is now demonstrated rather than inferred.

**Now settled, and settled the good way — see F5.** APNs *does* report a genuinely dead
activity: `410 ExpiredToken`, carrying the exact invalidation instant. So the picture is
asymmetric, and the asymmetry is the actionable part:

| | Can the backend tell? |
|---|---|
| This activity is **gone** | **Yes** — `410 ExpiredToken`, authoritative, timestamped (F5) |
| This update **rendered** | **No** — `200` regardless (F6, demonstrated three ways) |
| This payload was **undecodable** | **No** — `200`, and nothing happens on device (F6) |

A backend can therefore build reliable *lifecycle* state and cannot build any *delivery*
state. Reconciliation and cleanup are tractable; delivery confirmation is not, and must either
come from the device or be designed around.

An earlier draft of this finding treated the 16:57:10 `la-update` as evidence of a 200-to-dead-
token. It was not — the activity was alive. The real evidence arrived eight hours later and
pointed the opposite way.

---

## F3 — Every budget number this workstream produces is a *frequent-updates* number.

**Question.** What qualifies the update-budget measurement?

**Evidence.** `Sources/App/Info.plist` sets `NSSupportsLiveActivitiesFrequentUpdates = true`.
Apple's widely-quoted "~4 updates/hour" describes the *default* budget, with this key absent.
These are different quantities.

**Answer.** E2's ceiling is the frequent-updates ceiling on a device where the user has not
turned that setting off — and users *can* turn it off, per-app, in Settings. So the product
faces two different budgets in the field depending on a toggle it does not control.

**Consequence.** The design must decide explicitly whether to ship the key, and must degrade
sanely for users who disable it. Measuring the default budget needs a second build and a
reinstall; recorded in PROTOCOL.md under "Not measured" unless time allows a second pass.

**Confidence: high** — it is a fact about the build, read directly from the plist.

---

## F4 — The probe app could not capture a push-started activity's push token. A production app must.

**Question.** After the backend starts an activity by push, how does it get the per-activity
token needed to *update* that activity?

**Evidence.** `LiveActivityController.observe(_:)` wires `pushTokenUpdates` only for
activities the app started itself (`startLocally()` sets `current`). A push-started activity
never passes through that path, so its token was never observed, never printed, and never
reached `tokens.md`. The consequence was concrete: after the 16:57 push-to-start, there was no
way to send that activity a single update.

**Answer.** The app must observe `Activity<T>.activityUpdates` — the async sequence of
activities appearing by any route — and register `pushTokenUpdates` for each, including ones
it did not create. Anything less silently loses the ability to update exactly the activities
the backend started, which is the product's entire primary flow.

**Why this counts as a finding rather than a prototype bug.** The push-to-start flow has an
asymmetry that is easy to miss: the *server* initiates, but only the *client* can learn the
resulting token, and only if it is listening on the right sequence. A production app that
wires token capture into its own start path — the obvious way to write it — will pass every
local test and fail in the field. This belongs in `push-flow.md`.

**Confidence: high** — read from the source, and confirmed by the missing token in practice.

---

## F5 — RESOLVED. On iOS 26.5 a Live Activity's push token dies at 8 hours, and APNs reports it as `410 ExpiredToken` carrying the exact invalidation instant.

**Question.** Does a Live Activity end at a fixed age, and can a backend find out?

**Evidence.** 27 `la-update` heartbeats to one per-activity token, from a detached process,
2/hour then 12/hour across the expected window. The transition is unambiguous:

| Heartbeat | Wall clock (EDT) | Elapsed | APNs |
|---|---|---|---|
| hb=024 | 2026-09-07 00:35:00 | 7 h 50 m | `200` |
| hb=025 | 2026-09-07 00:40:00 | 7 h 55 m | `200` |
| **hb=026** | **2026-09-07 00:45:00** | **8 h 00 m** | **`410 ExpiredToken`** |
| hb=027 | 2026-09-07 00:50:00 | 8 h 05 m | `410 ExpiredToken` |

25 consecutive `200`s, then `410`, then `410` again on confirmation. No degradation, no
partial state, no warning.

**The 410 response body carries `timestamp: 1788756241000` — 2026-09-07 00:44:01 EDT.** That is
APNs reporting the precise second the token became invalid, not a bracket. The experiment was
designed to bracket the transition to ±5 minutes; the platform handed back an exact instant.

**Answer, two parts.**

**(a) The per-activity push TOKEN dies at 8 hours.** Note the careful wording — what was
directly measured is the token's lifetime, not the activity's. The activity's start time was
only known to ±10 min (started by hand during the S3 runbook), so the direct reading is "died
8 h 00 m ± 10 min after an estimated start". But the death instant is known exactly, so the
inference runs the other way: an exactly-8-hour lifetime back-solves a start of **16:44:01
EDT**, which sits inside the independently-derived window (the human captured that activity's
token between ~16:39 and ~16:55). Two unrelated lines of evidence agreeing is why this is
stated as 8 hours rather than "about 8 hours".

**That the *activity* also ended at that moment is an inference, not a measurement.** Token
invalidation and the card leaving the Lock Screen are separate events and this run cannot
separate them — the morning observation can. Keeping them apart matters more than it looks:
if a card can outlive its token, users see a stale card the backend has no way to reach or
correct, and the whole delivery picture changes. This distinction is unaffected by F9.

**(b) A backend CAN detect a dead Live Activity.** This is the half that was genuinely in doubt,
and the answer is the good one. `410 ExpiredToken`, with an exact timestamp, is a reliable
negative signal. Restart reconciliation is therefore tractable: store the token, push to it,
treat 410 as authoritative death, and the timestamp even says when. `operations.md` can specify
that concretely instead of hedging.

**What this does NOT overturn — the distinction matters.** F2 stands unchanged. APNs still gives
no *positive* delivery signal: a `200` means nothing about whether a live activity rendered
anything, as F6 demonstrated three times over. What F5 adds is that the *terminal* state is
observable. So a backend can know an activity is **gone**; it still cannot know an activity is
**working**. Those are different guarantees and the design should not conflate them.

**Confidence: high.** 27 samples, a sharp single transition, a confirming repeat, and a
server-reported timestamp that agrees with an independently-estimated start.

### F8b — restart reconciliation, HALF answered (revised after F9)

Every one of those 27 heartbeats was sent from a process with **no `Activity` handle and no
memory of having started anything** — only a token read from a file. That is exactly the
"backend restarted and lost its state" case in `operations.md`.

**What that demonstrates:** a stored token stays addressable for the activity's whole life from
a process that knows nothing else about it, and then reports its own death cleanly. Cleanup and
reconciliation can be built on that.

**What it does NOT demonstrate, and an earlier revision of this finding wrongly claimed it
did:** that content from such a process actually reaches the card. Per F9, those heartbeats
carried an ISO-8601 `updatedAt` — the encoding F6 proved undecodable — so the strong prediction
is that none of them rendered. The token was exercised; the delivery path was not.

**E8 therefore stands as: token addressability and death detection — answered. Content delivery
from a stateless process — not answered by this run.** The missing half costs minutes once the
instrumented build is in (it is E0's calibration), not another eight hours.

### Still open on the user-visible side

Whether the *card* left the Lock Screen at 00:44:01 alongside the token, or lingered, or had
already stopped presenting content earlier (F7's loading indicator). Token death and card
disappearance are not the same event and this run cannot separate them. The morning observation
does — and B2/B3, push-started at 17:11:53–55 with start times known to the second, expire at
~01:12 if the 8-hour cap is uniform, giving a second and much better-pinned reading.

---

## Still open

Everything else. E0 (instrument calibration), E1 (push-to-start reliability across
force-quit / reboot / before-first-unlock / Low Power Mode), E2 (update budget), E3
(collapse-id), E5 (concurrency), E6 (ending and `dismissal-date`), E7 (Watch mirroring —
blocked on whether a Watch is paired), E8 (restart reconciliation), E9 (widget background
push). Designs for all of them are in PROTOCOL.md, each with its falsifier.

---

## F6 — RESOLVED. On iOS 26.5, ActivityKit's push decoder rejects an ISO-8601 string for a Swift `Date`. It requires a JSON **number**. One wrong field silently kills the entire push.

**Answer.** Push-to-start works. It had been failing on the encoding of a single field.

**Evidence.** Three push-to-start pushes at 17:11:53–55 EDT, identical in every respect except
the JSON encoding of `ContentState.updatedAt`, each tagged with its own `attributes.routeName`
so the Lock Screen names the winner. Human observation:

| Arm | `updatedAt` sent as | APNs | Card appeared |
|---|---|---|---|
| `S4-B1-iso` | `"2026-09-06T21:11:53Z"` (ISO-8601 string) | 200 | **no** |
| `S4-B2-epoch` | `1788729113` (number, Unix epoch) | 200 | **yes** |
| `S4-B3-ref2001` | `810421913` (number, seconds since 2001-01-01) | 200 | **yes** |

**The delta between the failing A1 and the working B2 is exactly one thing: `updatedAt` went
from a JSON string to a JSON number.** Nothing else changed — same topic, same token, same
`attributes-type`, same key spellings, same five `content-state` keys. All three arms returned
`200`, so APNs distinguished none of them.

**Human-confirmed on a second channel.** Each arm carried an `aps.alert` titled with its own
name. The user reported seeing **exactly two banners — `S4-B2-epoch` and `S4-B3-ref2001`.
`S4-B1-iso` produced nothing at all.** So the split is directly observed twice over, on two
independent surfaces, rather than inferred from card presence alone.

**And that second channel says something the first could not: the alert dies with the
`ContentState`.** `aps.alert` is a sibling of `content-state` in the payload, not a child of
it, so a reasonable person would expect the banner to survive a content-state decode failure.
It does not. **One bad field discards the whole push — the activity and the user-visible
notification with it.** A backend cannot fall back on "at least the alert got through".

**Mechanism.** `ContentState.updatedAt` is a Swift `Date`. `JSONDecoder`'s default
`dateDecodingStrategy` is `.deferredToDate`, which expects a number. Handed a string it throws,
the *whole* `ContentState` fails to decode with it, and ActivityKit creates nothing and reports
nothing to anyone. A single mistyped field discards the entire push, silently, behind a 200.

**Hard requirement on the production payload, and it is not obvious.** Any `Date` in a
`ContentState` must be sent as a **JSON number**, never as an ISO-8601 string — which is what a
reasonable backend engineer would write, what Apple's own DTS guidance suggested to S2, and
what every other JSON API in this system will use. *Which* numeric epoch the decoder reads it
against is not yet pinned (see below); that the value must be numeric is established. A trap with no
diagnostic: no APNs error, no device log a server can see, no partial render. It cost this
project two failed pushes and most of an afternoon, and the same mistake in production would
present as "Live Activities just don't work" with nothing to debug.

**Cheapest mitigation for layer 2: do not put a `Date` in `ContentState` at all.** Send an
integer of epoch seconds and convert client-side. That removes the failure mode rather than
documenting it, and `display-contract.md`'s content-state field set is still Open, so the
decision is free to make now.

**Note that B2 and B3 both rendered.** Both are numbers, so both decode; they differ only in
the *value* produced. B2's Unix-epoch number, read as seconds-since-2001, lands in the year
2058. So "the card appeared" does not by itself confirm the strategy is `.deferredToDate` —
the value shown on the card does, and that is the outstanding one-line check.

**Confidence: high** that a JSON number is required and a string fails — three arms, one
variable, unambiguous split, direct human observation. **Medium** that the strategy is
specifically `.deferredToDate` rather than some other numeric interpretation; the card's
timestamp line settles it.

**Retracted:** an earlier revision of this finding said the corrected push-to-start "started
nothing" and named that the workstream's headline negative. That was correct as of 17:06 and
is now superseded — it was a payload defect, not a platform limitation. The negative stood for
about two hours. Kept visible rather than deleted, because the sequence is the lesson: two
separate payload bugs, four `200 OK`s, and nothing discovered until somebody looked at a phone.

### Superseded diagnosis (retained for the record)

**Question.** S2 root-caused the first push-to-start failure to snake_case keys and fixed it.
Does a payload whose keys match S3's Swift structs exactly start a Live Activity?

**Evidence.** 16:57:09 EDT, `la-start` to the push-to-start token, `attributes {routeName:
"S4-A1", stopName: "Boston Landing"}`, `content-state` with all five of S3's keys spelled
correctly. APNs `200`, `apns-id e32ed27b-…`. Human observation of the Lock Screen at ~17:06:
**one card, and it is the locally-started one.** No `S4-A1` card.

**Answer: the snake_case fix was necessary but not sufficient. Push-to-start is failing for a
second, independent reason, and it fails silently** — iOS creates nothing and reports nothing
to anyone. This is the assumption `docs/architecture.md` decision 3 rests on, so it is the
most important open thread in the workstream.

**Leading hypothesis — `ContentState.updatedAt` is a Swift `Date` and we are encoding it
wrongly.** S2 shipped ISO-8601 on DTS guidance at explicitly medium confidence and flagged it
as its one unresolved payload question. But `JSONDecoder`'s *default* `dateDecodingStrategy`
is `.deferredToDate` — a bare number of seconds since 2001-01-01. If ActivityKit's push
decoder is a stock `JSONDecoder`, an ISO-8601 *string* cannot decode into a `Date`, the whole
`ContentState` fails with it, and no activity is created. One wrong field kills the entire
push. That single cause would explain both open failures at once: the push-to-start that
started nothing and the `la-update` that may never have applied.

**Test in flight (E1b, sent 17:11 EDT).** Three push-to-start sends identical but for the
encoding of `updatedAt`, each with a distinct `routeName` rendered on the card's top line:
`S4-B1-iso` (ISO-8601 string), `S4-B2-epoch` (Unix seconds), `S4-B3-ref2001` (seconds since
2001). One glance at the Lock Screen names the winner. Each also carries a distinctly-titled
banner, so a banner arriving without a card separates "never processed" from "processed and
the content rejected".

**What would falsify the hypothesis.** All three arms produce no card. Then `updatedAt`
encoding is not the cause and push-to-start is failing structurally on this device — a much
more serious result, and one that would change the product's shape rather than its payload.

**Confidence in the failure: high** (direct human observation). **Confidence in the cause:
none claimed** — it is a hypothesis with a designed test outstanding, deliberately not
written up as an answer.

**Note on cost.** Two push-to-start failures have now been diagnosed only because someone
looked at the phone. Both returned 200. This is the third independent confirmation of the
governing constraint at the top of this file.

---

## F7 — REFRAMED. The loading indicator is an overlay on correctly-rendered content, not a failure. Cause still open, and it may be a feature.

**Resolved by a second human observation:** *"the no push started with real text and I can
still see real text under the loading symbol."*

**That kills the two dangerous readings outright.** The widget extension **is** installed and
**is** rendering — so instrument I1 (the render log) is viable, and "a Live Activity can be
started locally on this device" is now **confirmed** rather than assumed. Both of those were
load-bearing for the rest of the workstream, and both were genuinely in doubt for a couple of
hours: S3 had recorded that the widget target's signing was never separately verified, and a
`.appex` that failed to install would have produced exactly the symptom reported.

**What remains is an activity that renders correctly *and* carries a progress/loading
affordance.** Most likely a staleness or pending-update signal from iOS rather than an error.
One check I can already report: **the probe passes `staleDate: nil`** on local start
(`LiveActivityController` line 50), and none of S2's push payloads set `aps.stale-date`. So
whatever produces the overlay, it is **not** an explicit stale date we set — either iOS
applies a default staleness window when given none, or the affordance means something else.
E10 (below) tests it directly by setting one deliberately.

**Why this could be a product finding rather than a bug.** If iOS marks a Live Activity as
visibly stale on its own, the platform provides a freshness signal for free, and the cost of a
missed update drops: the user is told the content may be old rather than being silently shown
a lie. That interacts directly with the update-budget question and with the honest-freshness
problem in `push-flow.md`, which currently assumes the app must solve it. Worth knowing before
that gets designed.

**Confidence: high** that the overlay is not a rendering failure. **No cause claimed.**

### Superseded — the three hypotheses as first written

**Evidence.** The human's 17:06 report: the one card present is "the no_push live activity
with a loading symbol". The locally-started activity exists and is addressable (E4's
heartbeats to its token are returning 200), but it is not presenting content.

**Why this is not a footnote.** The candidate explanations have very different consequences:

1. The widget extension has never successfully rendered — S3 recorded that the widget
   target's signing was **never separately verified**, and a `.appex` that did not install
   would produce exactly this. If so, instrument I1 (the render log) cannot work at all and
   E2/E3 need redesign — and "a Live Activity can be started locally" is itself unconfirmed.
2. The S4-A2 `la-update` at 16:57:10 landed and drove the activity into a state the installed
   widget cannot render. **If an update can push a live activity into a permanently-broken-
   looking state, that is a first-order product finding** — worse than an update not landing,
   because the user sees something wrong rather than something merely stale.
3. The activity is stale and iOS is showing a degraded presentation (though S3 sets
   `staleDate: nil`).

**Discriminator, costing one question:** has that card *ever* shown its real text ("Local
start — no push involved")? Never → explanation 1. Yes, until 16:57 → explanation 2. It is
in the outstanding human ask.

**Confidence: the observation is high; the cause is unknown and no cause is claimed.**

---

## F8 — Three Live Activities coexisted on one device, unprompted. Partial concurrency data at no cost.

**Evidence.** At ~17:15 EDT the human volunteered: "I now have 3 total live activities, the no
push, S4-B2-…, & S4-B3-…". Nobody designed this; it fell out of E1b starting two activities
while one was already running.

**Answer so far.** On iOS 26.5, **at least 3** simultaneous Live Activities from one app are
permitted and all three are individually identifiable on the Lock Screen — the human read three
distinct `routeName` values off three distinct cards, which also confirms they are presented
separately rather than collapsed into one stack summary. The documented 5-per-app cap is not
contradicted; it is simply not yet reached. E5 still has to push past 5 to find the boundary and
the failure mode, which is the part with design consequences.

**Confidence: high** for "≥3 coexist, separately presented"; **nothing claimed** about the cap.

### The free bonus that matters more

B2 and B3 were started by push at **17:11:53 and 17:11:55 EDT — start times known to the
second.** The activity E4 is heartbeating was started by hand during the S3 runbook and its
start time is known only to ±10 minutes.

So the morning observation gets a far better 8-hour-cap measurement than E4 was designed to
produce, for free: if the cap is 8 h, B2 and B3 should be gone by ~01:12, and whether they are
still present at the morning look brackets the true lifetime against a start time with no
uncertainty in it. E4's heartbeats remain the only way to answer the *other* half — whether a
sender can detect the death — because there is no per-activity token for a push-started
activity on this build (F4).

**Consequence for the morning ask:** it must name B2 and B3 specifically, not just ask "are the
cards still there".

---

## F9 — E4's heartbeats carried the one encoding F6 proved fatal. My error, caught before the confirming observation arrived.

**What happened.** All 27 of E4's heartbeats sent `content-state.updatedAt` as an
**ISO-8601 string**:

```
"content-state": {"v":1, "displayStatus":"delayed",
                  "headline":"S4-E4 hb=001 elapsed=0h30m",
                  "minutesToDeparture":6,
                  "updatedAt":"2026-09-06T21:15:00Z"}
```

`e4_cap.py` used S2's `example_payload("la-update")` and left `refresh_la_fields` at its
default, which rewrites `updatedAt` to a fresh ISO-8601 string on every send. Six hours later
F6 established that an ISO-8601 string is precisely what ActivityKit's push decoder cannot
decode into a Swift `Date`, and that one bad field discards the entire push.

**So the strong prediction is that none of them ever reached the card.** They
returned 26 `200 OK`s regardless. This is a fourth independent instance of F6's mechanism, and
this time I walked into it myself while holding the finding that describes it.

**How it was caught.** Not by the device, and not by me reviewing my own work — the
orchestrator asked me to pre-register which conclusions would move if the pending observation
(A4: what text was actually on the card) came back unfavourably. Working out what would have to
change is what sent me to check the sent payloads. Worth recording as a process point: the
request to state in advance what would falsify a result is what surfaced the defect, before any
answer arrived to argue with.

### What survives, what changes — registered in advance of A4

| Claim | Status if A4 shows push text | Status if A4 shows the original local-start text |
|---|---|---|
| Token dies at exactly 8 h | **holds** | **holds** — APNs token validity does not depend on whether the app could decode the body |
| `410 ExpiredToken` is a reliable death signal | **holds** | **holds** — same reason |
| The *activity* ended at 8 h | holds | **inference only** — what was measured is token lifetime; card disappearance is A1/A3's job |
| A stateless backend can *drive* an activity by stored token | **holds** | **retracted** — see below |
| APNs `200` carries no delivery information | holds | **strengthened**, though by my bug rather than a platform failure |

**The claim I am retracting in advance, because it is the one I would be tempted to keep.**
F5 and F8b said a backend that lost all in-memory state "can keep pushing to an activity it did
not start, using only a stored token", and I wrote that it answered PROTOCOL.md E8 without a
separate experiment. That is too strong. What 27 heartbeats from a stateless process actually
demonstrated is that **a stored token stays addressable for 8 hours and then reports its own
death** — real, useful, and enough to build cleanup and reconciliation on. It did **not**
demonstrate that content from such a process reaches the card, because the content was
defective. Those are different claims and I conflated them.

E8 therefore stands as: **token addressability and death detection — answered. Content delivery
from a stateless process — not answered by this run.**

**Cost to fix: minutes, not another eight hours.** The delivery half needs a numeric
`updatedAt` and the render log, which is exactly E0's calibration. It does not need the cap
re-run. `e4_cap.py` is fixed (numeric `updatedAt`, `refresh_la_fields=False`) so a repeat is
correct if one is ever wanted.

**Confidence: high** that the heartbeats were undecodable, and the basis is stated precisely
because this finding is itself a retraction:

- **The bodies were recorded, not inferred from code.** S2's `logs/send-history.jsonl` logs the
  post-mutation payload for every send. All **27** E4 sends have a recorded body, and **27 of
  27** carry `updatedAt` as an ISO-8601 string; zero carry a number. Verified by
  `harness/check_e4.py`, which is committed so the check is repeatable.
- **What that is not:** a packet capture. It is the sender's own record of the body it handed
  to the HTTP client, taken at send time. Short of a wire trace, it is the strongest available
  evidence, and it is a category better than reading the code path.
- **My own `logs/e4.log` carries status codes only** and no payload bodies. An earlier revision
  of this finding said "the sent payloads are logged" without naming the file, which invited
  exactly the wrong one to be checked.

The prediction is registered here **before** A4 is answered.

### A landmine for anyone else using S2's harness

The harness's `refresh_la_fields` default silently rewrites `content-state.updatedAt` to an
ISO-8601 string on every Live Activity send. Given F6, **that default now reintroduces a fatal
payload defect on every call that relies on it**, and it does so invisibly, behind a 200. Any
future caller must pass `refresh_la_fields=False` and supply a numeric date, or the default must
change. Flagged to the orchestrator rather than edited directly, since the harness is S2's.

---

## F10 — Which epoch a numeric `Date` is read against: OPEN, and pre-registered here before either observation lands.

F6 established that a Swift `Date` in a pushed `ContentState` must be a JSON **number**; an
ISO-8601 string kills the whole push. It did **not** establish which epoch the number is read
against, because both numeric arms rendered — they differ only in the *value* produced, and
nobody has yet read a value.

**This is live divergence, not a hypothetical.** S4's `e1_pts_conditions.py` sends seconds
since **2001-01-01**. S2's harness default (b7cf51b) sends seconds since **1970**, matching
`aps.timestamp`. Both render. They cannot both display the correct wall clock, and the gap is
about 31 years.

### Registered predictions, before A2 or E0 answers

| If the decoder is… | `S4-B2-epoch` (Unix number) shows | `S4-B3-ref2001` (2001 number) shows |
|---|---|---|
| `.deferredToDate` — seconds since 2001 (JSONDecoder's default) | a date around **2057** | **6 Sep 2026, ~5:11 PM** — correct |
| seconds since 1970 | **6 Sep 2026, ~5:11 PM** — correct | a date around **1995** |

Exactly one card reads correct and one reads absurd. **Which is which is the answer**, and the
two outcomes are cleanly separable — there is no result that is consistent with both.

**Two independent instruments will report it**, and they should agree:
- **A2**, the human transcribing a card's bottom line. Cheap, available now, but it is a small
  line under a loading overlay.
- **E0**, the instrumented build logging the *decoded* `updatedAt` as an ISO timestamp from
  `contentUpdates`. Unambiguous, needs no interpretation, minutes once installed.

If they disagree, the instrument wins and the disagreement is itself worth chasing.

**A bias I introduced and then removed.** The runbook's A2 originally told the human that "a
date in 2057" was the expected result — which is true only under the first hypothesis, and
naming it in the question invites the answer. It now asks them to transcribe what is there and
says explicitly that which card is wrong is what we do not know. Recorded because a leading
question in a measurement instrument is the same class of defect as a payload that silently
fails to decode: it produces a confident answer that was never actually measured.

**Deliberately not guessing in the meantime.** Picking an epoch now to make the two senders
agree would risk a second silent wrongness of the same family as F6 — renders fine, shows a
nonsense date, nobody notices until a user sees it. The divergence is harmless for Part C,
which reads card *names*, not dates, so nothing is blocked on it.

**Confidence: none claimed. Open by design**, with the outcome table written down first so
whichever answer arrives cannot be rationalised into the one I expected.
