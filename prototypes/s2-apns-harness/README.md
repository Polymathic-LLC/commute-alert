# S2 — APNs push harness

A standalone Python tool that sends all five push shapes S4 needs (Live Activity
update / push-to-start / end, alert, background) to a device, so S4 can measure
Live Activity behavior without also debugging push plumbing.

Not production code. See [`../../DERISKING.md`](../../DERISKING.md) workstream S2.

## Layout

```
apns_harness/
  config.py     credential loading (.secrets/apns.env + .p8), S3-probe defaults
  defaults.py   authoritative S3-probe identifiers (team, bundle ids)
  jwt_auth.py   ES256 provider-token signing + caching
  payloads.py   push-type table, header derivation, payload validation, examples
  client.py     HTTP/2 APNs client, response parsing, reason-code hints
  tokens.py     read the 3 device tokens from S3's tokens.md
  history.py    append-only send log (logs/send-history.jsonl, gitignored)
  cli.py        the CLI
payloads/       committed example payload files, one per push type
tests/          unit tests (no network, no real creds)
```

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp apns.env.example .secrets/apns.env      # then fill in APNS_KEY_ID
# drop the key at .secrets/AuthKey_<KEYID>.p8
```

`.secrets/`, `.venv/`, and `logs/` are gitignored.

## Use

```
# check what's wired up (no creds needed)
.venv/bin/python -m apns_harness doctor

# see / write an example payload
.venv/bin/python -m apns_harness example la-start

# build the exact request without sending (no creds, no network)
.venv/bin/python -m apns_harness send --type la-start --example --token <hex> --dry-run

# send for real (needs .secrets/ populated)
.venv/bin/python -m apns_harness send --type la-start  --payload payloads/live-activity-start.json  --token-role pts
.venv/bin/python -m apns_harness send --type la-update --payload payloads/live-activity-update.json --token-role activity
.venv/bin/python -m apns_harness send --type la-end    --payload payloads/live-activity-end.json    --token-role activity --dismissal-in 900
.venv/bin/python -m apns_harness send --type alert      --payload payloads/alert.json              --token-role device
.venv/bin/python -m apns_harness send --type background --payload payloads/background-widget.json   --token-role device

# what was sent
.venv/bin/python -m apns_harness history -n 20
```

### Token resolution order (for `send`)

1. `--token <hex>`
2. `--token-file <path>`
3. `--token-role {pts,activity,device}` → read from S3's `tokens.md`
4. implied role from `--type` (`la-start`→pts, `la-update`/`la-end`→activity,
   `alert`/`background`→device) → read from S3's `tokens.md`

S3's `tokens.md` is auto-discovered at `prototypes/s3-apple-setup/tokens.md`
in the main checkout (S2 may run in a worktree). Override with `--tokens-file`
or `$S3_TOKENS_FILE`.

The reader matches S3's real format — a `## Tokens` fenced block with each token
on the line *after* its label (`LIVE ACTIVITY push-to-start token:` etc.) —
and also tolerates `key: value`, bullet, and table-row layouts. An unfilled
`<paste …>` placeholder is reported as "not filled in yet", never silently
skipped.

### Key headers (handled automatically)

| `--type`     | `apns-push-type` | `apns-topic`                       | `apns-priority` |
|--------------|------------------|------------------------------------|-----------------|
| `la-update`  | `liveactivity`   | `<bundle>.push-type.liveactivity`  | 10              |
| `la-start`   | `liveactivity`   | `<bundle>.push-type.liveactivity`  | 10              |
| `la-end`     | `liveactivity`   | `<bundle>.push-type.liveactivity`  | 10              |
| `alert`      | `alert`          | `<bundle>`                         | 10              |
| `background` | `background`     | `<bundle>`                         | 5               |

The Live Activity topic suffix `.push-type.liveactivity` is the classic silent
failure — the harness never lets it be forgotten, and defaults the bundle id to
the S3-probe value with a loud warning if `apns.env` is missing it.

`aps.timestamp` is injected fresh on every Live Activity send unless the payload
already sets one (Apple orders LA updates by it). `content-state.updatedAt` is
refreshed to now as a **number** (Unix epoch seconds) too, unless
`--keep-updated-at`.

The `la-*` example payloads' `attributes` / `content-state` keys match S3's
`CommuteActivityAttributes` Swift struct **exactly** (`routeName`, `stopName`,
`displayStatus`, `headline`, `minutesToDeparture`, `updatedAt`, `v`). ActivityKit's
push decoder does not convert snake_case and rejects missing non-optional keys —
a mismatch means APNs returns 200 and iOS silently starts/updates nothing.
`updatedAt` maps to a Swift `Date`: it **must be a JSON number** (Unix epoch
seconds), not a string — S4's E1b showed on device that a string discards the
whole push behind a `200 OK`. The harness's validator rejects a string there.

## Library use (rate ramps, e.g. S4)

Driving the CLI in a subprocess per send opens a new HTTP/2 connection and mints
a new provider JWT every time — at rate that trips `TooManyProviderTokenUpdates`.
Use `apns_harness.api.Sender` instead: one pooled connection + one cached JWT for
the whole loop, every send in the same `logs/send-history.jsonl`.

```python
from apns_harness.api import Sender
from apns_harness.payloads import example_payload

with Sender(environment="sandbox") as s:
    for i in range(200):
        resp = s.send(
            type="la-update",
            token=per_activity_token,
            payload=example_payload("la-update"),
            headline=f"ramp {i}",
            collapse_id="ramp",
            extra_log={"seq": i},
        )
        assert s.provider_token_refreshes == 1   # stays 1 across the whole ramp
```

`send()` → `ApnsResponse`; `send_detailed()` → `(BuiltRequest, ApnsResponse, record)`.
The CLI's own send path goes through `Sender`, so the two are one code path.

## Tests

```
.venv/bin/python -m pytest -q
```
