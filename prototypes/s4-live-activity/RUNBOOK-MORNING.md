# S4 — morning device session

One sitting. **Part A is 2 minutes and is time-sensitive — do it before touching anything
else, including before unlocking the phone.** Parts B and C are ~20 minutes together and can
happen any time after.

Route questions and answers through the orchestrator, not to S4 directly.

---

## Part A — before you unlock the phone (2 min)

Everything in Part A is destroyed by unlocking, rebuilding, or opening the app. Please do it
first.

**A1. Wake the screen. Do not unlock.** Which of these cards are on the Lock Screen?

| Card (grey top line) | Still there? | If gone, roughly when last seen? |
|---|---|---|
| the no-push one (`CR-Worcester`) | | |
| `S4-B2-epoch` | | |
| `S4-B3-ref2001` | | |

**A2. For any card still present, read me its small bottom line.** It looks like
`v1 · 5:11:53 PM`. **The time on that line is the measurement** — copy it exactly, including
AM/PM. If a card shows a wildly wrong time (a date in 2057, say), that is the expected
result for one of them, not a bug — it is precisely what we are trying to find out.

**A3.** Did the no-push card disappear at around **00:44** last night? Anything you remember
about when it went is useful, even "it was gone when I woke up".

**A4. A memory question, and it may be the most valuable thing in this list.** When you
looked at the no-push card yesterday around 17:20 and saw real text under the loading symbol
— **do you remember what that text said?** Specifically, did it look like

- `Local start — no push involved`  ← the text it was created with, or
- `S4-E4 hb=001 elapsed=0h30m`  ← text that only a push could have put there

If you genuinely don't remember, say so — a guess here is worse than nothing.

> Why A4 matters: 27 pushes went to that activity over eight hours, and 25 of them came back
> from Apple's servers as successes. Whether a single one reached the screen is unknown — and
> we now have good reason to think none did, because those pushes carried a date format we
> later proved the phone silently rejects. If the card still showed its original text, that is
> confirmed, and every one of those "successes" was fictional.

---

## Part B — install the instrumented build (~10 min)

The hold is lifted; the overnight measurement finished early and nothing depends on the old
build now.

1. Open **`prototypes/s4-live-activity/probe-app/S3Probe.xcodeproj`**.
   **Note the path — this is a different project from the one you used yesterday.** Same app,
   same bundle ID, same team, so signing should need no new setup. If Xcode asks to register
   anything, let it.
2. Select the **S3Probe** scheme and your iPhone, then ⌘R.
3. When the app opens, check the **S4 — instrument** section: `App Group container` should say
   **ok**. If it says `MISSING`, stop and report that — the log has nowhere to go and the rest
   of the session is pointless.
4. Tap **Refresh / snapshot**. Tell me what the snapshot lines say (they list every live
   activity the app can see, with its state).

Installing replaces the app, which ends any Live Activities still running. That is expected
and fine — Part A has already captured what mattered.

---

## Part C — push-to-start reliability (~20 min, clock-driven)

This is the question the whole product rests on: can the backend start a Live Activity with
no user interaction, whatever state the phone is in?

**How this works.** You follow a timetable. I send pushes on the same timetable. You never
wait on me and I never wait on you — just do each step at the stated time and write one line.
**Pick a start time, tell the orchestrator, and start on the minute.** Call it T.

| Time | What you do |
|---|---|
| T+0:00 | Open S3 Probe, then swipe it away in the app switcher (**force-quit**). Lock the phone, put it down. |
| T+3:00 | Wake the screen, don't unlock. **List every card name.** |
| T+4:00 | Force-quit again if it's open. Lock. |
| T+7:00 | Wake, don't unlock. **List every card name.** |
| T+8:00 | Turn **Low Power Mode** on (Settings → Battery). Force-quit the app. Lock. |
| T+11:00 | Wake, don't unlock. **List every card name.** |
| T+12:00 | **Reboot the phone.** Do **not** unlock it after it restarts — leave it on the passcode screen. |
| T+17:00 | Look at the Lock Screen, still without unlocking. **List every card name.** |
| T+18:00 | Now unlock once, but **do not open S3 Probe**. Lock again. |
| T+21:00 | Wake, don't unlock. **List every card name.** |
| T+22:00 | Turn Low Power Mode back off. Open S3 Probe, tap **Refresh / snapshot**, then **Export log to Files**. Then press home to background it (do **not** force-quit) and lock the phone. |
| T+25:00 | Wake, don't unlock. **List every card name.** This is the baseline — see below. |
| T+26:00 | Open S3 Probe and tap **End ALL activities**. Done. |

Log format — one row per check:

```
T+3    cards visible: ______________________________
T+7    cards visible: ______________________________
T+11   cards visible: ______________________________
T+17   cards visible: ______________________________
T+21   cards visible: ______________________________
T+25   cards visible: ______________________________
```

**Please list *every* card name you can see, not just the newest one** — write `none` if there
are none. Cards accumulate: a successful trial leaves its card on the Lock Screen, so by T+21
there could be several. Each push carries a different name (`S4-E1-C2-t1`, `S4-E1-C5-t1`, …),
so the list of names tells me exactly which trials worked. **"A card is there" is not the
answer — the names are**, because a leftover card from an earlier step looks identical to a
fresh one otherwise.

**If a step shows no new name, that is a result, not a mistake.** It is the single most
valuable outcome this session can produce, so please write it plainly rather than retrying or
waiting a bit longer to see if it turns up.

### Why the odd extra step at T+25

The last check is a **baseline**: the app has just been used and backgrounded normally, which
is the easiest possible condition for a push to start an activity. It exists so that an
all-negative run is still interpretable. If nothing works all session *including* the baseline,
the problem is the device or the build and the conditions tell us nothing. If the baseline
works and the others don't, then the conditions are the finding — and that finding would change
the product. Three extra minutes buys the difference between an answer and a shrug.

---

## Not in this session

Pairing the Apple Watch. It's worth doing and it's queued, but it's heavier than the rest and
the questions above block a design decision that mirroring does not. Separate sitting.
