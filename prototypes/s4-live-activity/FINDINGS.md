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
| 17:11:53–17:11:55 `la-start` ×3 | E1b arms, outcome pending | `200` ×3 |

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

**Confidence: medium, and deliberately not higher.** The decode-failure row is established
beyond doubt (S2 root-caused it against the Swift structs). The stale-token row is *not* yet
evidence of anything: **nobody has looked at that phone since 16:40, so we do not know the
activity was dead.** It may have been perfectly alive and the 200 entirely correct. E4 (F5)
is the designed test; this finding will be upgraded or corrected from its result. Recorded at
medium rather than high specifically so it does not harden into fact before it is tested.

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

## F5 — The 8-hour cap. RUNNING.

Started 17:33 EDT, 49 heartbeats to a 12-hour horizon (04:45 EDT). See PROTOCOL.md E4.
Reports: when the activity ends, and whether a sender can detect it at all (the second
question decides F2's final confidence). Human observation in the morning supplies the
user-visible half.

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

## F7 — A live Live Activity was observed showing a loading indicator rather than content. Unexplained.

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
