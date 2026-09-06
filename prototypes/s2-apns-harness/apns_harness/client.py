"""APNs HTTP/2 client using `.p8` provider-token auth.

Endpoints:
    sandbox : https://api.sandbox.push.apple.com:443
    prod    : https://api.push.apple.com:443
    path    : /3/device/<hex device or activity token>

The request is HTTP/2 only — APNs will not answer over HTTP/1.1. `httpx` with
the `h2` extra handles the ALPN negotiation.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import defaults
from .config import ApnsConfig
from .jwt_auth import ProviderTokenSigner
from .payloads import PushType

HOSTS = {
    "sandbox": "https://api.sandbox.push.apple.com",
    "prod": "https://api.push.apple.com",
}

# APNs `reason` strings worth explaining inline (subset; full list in Apple docs).
REASON_HINTS = {
    "BadDeviceToken": "token doesn't match this environment (sandbox vs prod) or bundle id",
    "DeviceTokenNotForTopic": "apns-topic doesn't match the token — for Live Activity it must be <bundle>.push-type.liveactivity",
    "TopicDisallowed": "apns-topic not permitted for this key/app",
    "ExpiredProviderToken": "provider JWT older than 1h — refresh it",
    "InvalidProviderToken": "JWT signature/kid/iss wrong, or key not enabled for APNs",
    "MissingProviderToken": "no authorization header sent",
    "TooManyProviderTokenUpdates": "provider JWT refreshed too often (>~1/20min)",
    "Unregistered": "token is no longer valid (app uninstalled / activity ended)",
    "PayloadTooLarge": "payload exceeds 4KB",
    "BadCollapseId": "apns-collapse-id longer than 64 bytes",
    "BadMessageId": "apns-id not a valid UUID",
    "IdleTimeout": "connection idle too long — reconnect",
    "ExpiredToken": "the (activity) token has expired",
    "InternalServerError": "APNs transient failure — retry with backoff",
}


@dataclass
class BuiltRequest:
    """Everything about the request, resolvable without credentials (for --dry-run)."""

    method: str
    url: str
    headers: dict[str, str]
    json_body: dict[str, Any]

    def redacted_headers(self) -> dict[str, str]:
        h = dict(self.headers)
        if "authorization" in h:
            h["authorization"] = "bearer <jwt>"
        return h

    def curl(self) -> str:
        parts = ["curl", "-v", "--http2", "-X", self.method, f"'{self.url}'"]
        for k, v in self.headers.items():
            shown = "bearer <JWT>" if k == "authorization" else v
            parts += ["-H", f"'{k}: {shown}'"]
        body = json.dumps(self.json_body)
        parts += ["-d", f"'{body}'"]
        return " ".join(parts)


@dataclass
class ApnsResponse:
    status_code: int
    apns_id: str | None
    apns_unique_id: str | None
    reason: str | None
    timestamp: int | None
    raw_body: str
    ok: bool = field(init=False)

    def __post_init__(self) -> None:
        self.ok = self.status_code == 200

    def hint(self) -> str | None:
        return REASON_HINTS.get(self.reason or "")

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "apns_id": self.apns_id,
            "apns_unique_id": self.apns_unique_id,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "hint": self.hint(),
            "raw_body": self.raw_body,
        }


def build_request(
    *,
    cfg: ApnsConfig | None,
    push_type: PushType,
    device_token: str,
    payload: dict,
    environment: str,
    priority: int | None = None,
    collapse_id: str | None = None,
    expiration: int | None = None,
    apns_id: str | None = None,
    topic_override: str | None = None,
) -> BuiltRequest:
    if environment not in HOSTS:
        raise ValueError(f"environment must be one of {list(HOSTS)}")
    host = HOSTS[environment]

    if topic_override:
        topic = topic_override
    elif cfg is not None:
        topic = push_type.topic(cfg)
    else:
        # dry-run without credentials: fall back to the S3-probe default so the
        # printed topic is the real one, not a placeholder.
        base = defaults.APP_BUNDLE_ID
        topic = f"{base}.push-type.liveactivity" if push_type.topic_kind == "liveactivity" else base

    if expiration is None:
        # LA updates: give APNs an hour to land the push rather than
        # discard-if-not-immediately-deliverable. alert/background: 0 (store one).
        expiration = int(time.time()) + 3600 if push_type.topic_kind == "liveactivity" else 0

    headers = {
        "apns-push-type": push_type.apns_push_type,
        "apns-topic": topic,
        "apns-priority": str(priority if priority is not None else push_type.default_priority),
        "apns-id": apns_id or str(uuid.uuid4()),
        "apns-expiration": str(expiration),
        "content-type": "application/json",
    }
    if collapse_id:
        headers["apns-collapse-id"] = collapse_id

    return BuiltRequest(
        method="POST",
        url=f"{host}/3/device/{device_token}",
        headers=headers,
        json_body=payload,
    )


def _parse_response(resp: httpx.Response) -> ApnsResponse:
    reason = None
    timestamp = None
    body = resp.text or ""
    if body.strip():
        try:
            j = resp.json()
            reason = j.get("reason")
            timestamp = j.get("timestamp")
        except json.JSONDecodeError:
            pass
    return ApnsResponse(
        status_code=resp.status_code,
        apns_id=resp.headers.get("apns-id"),
        apns_unique_id=resp.headers.get("apns-unique-id"),
        reason=reason,
        timestamp=timestamp,
        raw_body=body,
    )


class ApnsClient:
    def __init__(
        self,
        cfg: ApnsConfig,
        *,
        environment: str = "sandbox",
        timeout: float = 15.0,
    ) -> None:
        self.cfg = cfg
        self.environment = environment
        self.signer = ProviderTokenSigner(
            key_id=cfg.key_id, team_id=cfg.team_id, p8_pem=cfg.p8_pem
        )
        self._client = httpx.Client(http2=True, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApnsClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def send(
        self,
        *,
        push_type: PushType,
        device_token: str,
        payload: dict,
        priority: int | None = None,
        collapse_id: str | None = None,
        expiration: int | None = None,
        apns_id: str | None = None,
        topic_override: str | None = None,
        force_token_refresh: bool = False,
    ) -> tuple[BuiltRequest, ApnsResponse]:
        req = build_request(
            cfg=self.cfg,
            push_type=push_type,
            device_token=device_token,
            payload=payload,
            environment=self.environment,
            priority=priority,
            collapse_id=collapse_id,
            expiration=expiration,
            apns_id=apns_id,
            topic_override=topic_override,
        )
        headers = dict(req.headers)
        headers["authorization"] = self.signer.authorization_header(force=force_token_refresh)
        http_resp = self._client.post(req.url, headers=headers, json=req.json_body)
        return req, _parse_response(http_resp)
