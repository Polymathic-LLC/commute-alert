"""Push-type definitions, header derivation, and payload validation.

The five sends S2 must cover (DERISKING.md):

    la-update   Live Activity content-state update
    la-start    Live Activity push-to-start (iOS 17.2+)
    la-end      Live Activity end
    alert       standard interruptive notification
    background  background / widget wake (content-available)

The single most common silent failure is the Live Activity topic: it is
`<bundle-id>.push-type.liveactivity`, NOT `<bundle-id>`. All three la-* types
use that topic and `apns-push-type: liveactivity`.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

# Apple's documented ceilings. Live Activity payloads (whole body) must be <= 4KB;
# alert / background <= 4KB too for the practical APNs limit we care about here.
MAX_PAYLOAD_BYTES = 4096


class PayloadError(ValueError):
    """Payload is structurally wrong for the chosen push type."""


@dataclass(frozen=True)
class PushType:
    key: str
    apns_push_type: str          # value of the `apns-push-type` header
    topic_kind: str              # "bundle" or "liveactivity"
    default_priority: int
    la_event: str | None = None  # expected aps.event for Live Activity sends

    def topic(self, cfg) -> str:
        if self.topic_kind == "liveactivity":
            return cfg.liveactivity_topic
        return cfg.bundle_id


PUSH_TYPES: dict[str, PushType] = {
    "la-update": PushType("la-update", "liveactivity", "liveactivity", 10, "update"),
    "la-start": PushType("la-start", "liveactivity", "liveactivity", 10, "start"),
    "la-end": PushType("la-end", "liveactivity", "liveactivity", 10, "end"),
    "alert": PushType("alert", "alert", "bundle", 10),
    "background": PushType("background", "background", "bundle", 5),
}


def parse_payload(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PayloadError(f"{path}: invalid JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise PayloadError(f"{path}: top-level JSON must be an object")
    return data


def _content_state_bytes(payload: dict) -> int:
    cs = payload.get("aps", {}).get("content-state")
    return len(json.dumps(cs).encode()) if cs is not None else 0


def validate(payload: dict, push_type: PushType) -> list[str]:
    """Return a list of human-readable warnings; raise PayloadError on hard errors."""
    warnings: list[str] = []
    aps = payload.get("aps")
    if not isinstance(aps, dict):
        raise PayloadError("payload has no `aps` object")

    total = len(json.dumps(payload).encode())
    if total > MAX_PAYLOAD_BYTES:
        raise PayloadError(
            f"payload is {total} bytes; APNs limit is {MAX_PAYLOAD_BYTES}"
        )

    if push_type.topic_kind == "liveactivity":
        event = aps.get("event")
        if event is None:
            raise PayloadError("Live Activity payload needs `aps.event`")
        if push_type.la_event and event != push_type.la_event:
            warnings.append(
                f"aps.event is {event!r}; expected {push_type.la_event!r} for {push_type.key}"
            )
        if "timestamp" not in aps:
            warnings.append("aps.timestamp missing — Apple recommends it on every LA push")
        if event in ("update", "start") and "content-state" not in aps:
            raise PayloadError(f"aps.event={event!r} needs `aps.content-state`")
        cs_bytes = _content_state_bytes(payload)
        if cs_bytes > MAX_PAYLOAD_BYTES:
            raise PayloadError(f"content-state is {cs_bytes} bytes; limit {MAX_PAYLOAD_BYTES}")
        cs = aps.get("content-state")
        if isinstance(cs, dict):
            for k in DATE_CONTENT_STATE_KEYS:
                if isinstance(cs.get(k), str):
                    raise PayloadError(
                        f"content-state.{k} is a string ({cs[k]!r}). It maps to a "
                        "Swift `Date`; ActivityKit's push decoder needs a JSON "
                        "number (Unix epoch seconds) and silently drops the "
                        "entire push otherwise. See FINDINGS.md."
                    )
            for k, val in cs.items():
                if k not in DATE_CONTENT_STATE_KEYS and isinstance(val, str) and _ISO8601_RE.match(val):
                    warnings.append(
                        f"content-state.{k} looks like a datetime string ({val!r}) — "
                        "if it maps to a Swift `Date`, send it as a number instead"
                    )
        if event == "start":
            if "attributes-type" not in aps or "attributes" not in aps:
                raise PayloadError(
                    "push-to-start needs `aps.attributes-type` and `aps.attributes`"
                )
        if event == "end" and "dismissal-date" not in aps:
            warnings.append(
                "aps.event=end without `aps.dismissal-date` — system picks default dismissal"
            )
    elif push_type.key == "background":
        if aps.get("content-available") != 1:
            raise PayloadError('background push needs `aps.content-available: 1`')
        if "alert" in aps or "sound" in aps or "badge" in aps:
            warnings.append("background push carries alert/sound/badge — may be treated as user-visible")
    elif push_type.key == "alert":
        alert = aps.get("alert")
        if not alert or (isinstance(alert, dict) and not (alert.get("title") or alert.get("body"))):
            warnings.append("alert push has no alert.title/body — will not show a banner")

    return warnings


# S3's throwaway `CommuteActivityAttributes` (Sources/Shared/CommuteActivityAttributes.swift).
# The push `attributes` / `content-state` JSON keys must match these Swift
# property names EXACTLY — ActivityKit's push decoder does not convert
# snake_case. Getting this wrong = APNs returns 200 and iOS silently starts /
# updates nothing.
S3_ATTRIBUTES_TYPE = "CommuteActivityAttributes"
S3_ATTRIBUTES_KEYS = ("routeName", "stopName")
S3_CONTENT_STATE_KEYS = ("v", "displayStatus", "headline", "minutesToDeparture", "updatedAt")

# content-state keys that are a Swift `Date`. ActivityKit's push JSONDecoder
# requires a JSON **number** for these (verified on device by S4's E1b — the
# ISO-8601-string arm rendered nothing, both numeric arms rendered). A string
# here makes the WHOLE push undecodable, silently, behind a 200 OK. So the
# harness rejects a string in one of these fields.
DATE_CONTENT_STATE_KEYS = ("updatedAt",)

_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?")


def inject_timestamp(payload: dict, *, now: int | None = None) -> bool:
    """Set `aps.timestamp` to now if absent. Returns True if it changed.

    Apple orders Live Activity updates by `aps.timestamp`; a stale value can make
    an update be dropped as out-of-order. Committed example files omit it so the
    sender always stamps a fresh one.
    """
    aps = payload.get("aps")
    if not isinstance(aps, dict) or "timestamp" in aps:
        return False
    aps["timestamp"] = now if now is not None else int(time.time())
    return True


def refresh_updated_at(payload: dict, *, now: float | None = None) -> bool:
    """Set `aps.content-state.updatedAt` to a fresh **numeric** Unix-epoch
    timestamp (integer seconds since 1970). Returns True if it changed.

    `updatedAt` is a Swift `Date`. ActivityKit's push JSONDecoder requires a JSON
    **number** for a `Date` — verified on device by S4's E1b: the ISO-8601-string
    arm rendered NOTHING (one bad field discards the entire push, behind a
    `200 OK`), both numeric arms rendered. Earlier code here wrote an ISO-8601
    string on the mistaken belief that Apple DTS guidance allowed it; that was
    wrong and cost an 8-hour measurement run (S4's E4).

    Epoch choice: seconds-since-1970, matching `aps.timestamp`. Whether a
    different epoch (2001 reference) shows a more correct wall-clock time on
    device is a smaller open question — see FINDINGS.md; E1b has the data.

    Only rewrites when the key is already present (any type). Absent => left
    absent (the field is `Int?`-style optional on S3's struct... actually
    `updatedAt` is non-optional there, so the example payloads always carry it).
    """
    cs = payload.get("aps", {}).get("content-state")
    if not isinstance(cs, dict) or "updatedAt" not in cs:
        return False
    cs["updatedAt"] = int(now if now is not None else time.time())
    return True


def example_payload(push_type_key: str, *, bundle_id: str = "<bundle-id>") -> dict:
    """Illustrative payloads matching S3's throwaway `CommuteActivityAttributes`.

    The content-state field SET is still a placeholder — display-contract.md
    leaves the production shape Open pending S4 + S6 — but the field NAMES here
    are S3's real ones so push-to-start / update actually decode on-device.

    Live Activity examples omit `aps.timestamp`; the sender injects a fresh one
    (`inject_timestamp`) and refreshes `updatedAt` (`refresh_updated_at`).

    `updatedAt` is a NUMBER (Unix epoch seconds) — ActivityKit's push decoder
    rejects a string for a Swift `Date` and drops the whole push. The fixed
    value here is refreshed to now on every send."""
    cs = {
        "v": 1,
        "displayStatus": "delayed",
        "headline": "Next inbound train +6 min",
        "minutesToDeparture": 6,
        "updatedAt": 1_735_689_600,  # 2025-01-01T00:00:00Z; refreshed to now at send time
    }
    if push_type_key == "la-update":
        return {"aps": {"event": "update", "content-state": cs}}
    if push_type_key == "la-start":
        return {
            "aps": {
                "event": "start",
                "attributes-type": S3_ATTRIBUTES_TYPE,
                "attributes": {
                    "routeName": "CR-Worcester",
                    "stopName": "Boston Landing",
                },
                "content-state": {**cs, "displayStatus": "on_time",
                                  "headline": "Push-to-start from the S2 harness"},
                "alert": {
                    "title": "Commute monitoring started",
                    "body": "Watching the inbound train.",
                },
            }
        }
    if push_type_key == "la-end":
        # `dismissal-date` omitted on purpose — add it at send time with
        # --dismissal-in / --dismissal-date. Absent => system default (~4h).
        return {
            "aps": {
                "event": "end",
                "content-state": {**cs, "displayStatus": "on_time", "headline": "Commute ended"},
            }
        }
    if push_type_key == "alert":
        return {
            "aps": {
                "alert": {
                    "title": "Worcester Line delay",
                    "body": "Inbound trains delayed ~15 min near Newton.",
                },
                "sound": "default",
            }
        }
    if push_type_key == "background":
        return {"aps": {"content-available": 1}}
    raise KeyError(push_type_key)
