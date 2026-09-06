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


def example_payload(push_type_key: str, *, bundle_id: str = "<bundle-id>") -> dict:
    """Illustrative payloads. Field set for content-state is deliberately a
    placeholder — display-contract.md leaves it Open pending S6.

    Live Activity examples omit `aps.timestamp` on purpose; the sender injects a
    fresh one at send time (see `inject_timestamp`)."""
    cs = {
        "v": 1,
        "display_status": "delayed",
        "headline": "Next inbound train +6 min",
        "updated_at": 1_700_000_000,
    }
    if push_type_key == "la-update":
        return {"aps": {"event": "update", "content-state": cs}}
    if push_type_key == "la-start":
        return {
            "aps": {
                "event": "start",
                "attributes-type": "CommuteActivityAttributes",
                "attributes": {
                    "route_id": "CR-Worcester",
                    "stop_id": "place-WML-0091",
                    "direction_id": 1,
                    "window_label": "AM commute",
                },
                "content-state": cs,
                "alert": {
                    "title": "Commute monitoring started",
                    "body": "Watching the 7:10 inbound.",
                },
            }
        }
    if push_type_key == "la-end":
        # `dismissal-date` omitted on purpose — add it at send time with
        # --dismissal-in / --dismissal-date. Absent => system default (~4h).
        return {
            "aps": {
                "event": "end",
                "content-state": {**cs, "display_status": "on_time", "headline": "Commute ended"},
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
