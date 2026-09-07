"""In-process entry point for driving the harness in a loop.

Built for S4's update-budget ramp: a few hundred sends over an hour or two at
controlled intervals, all landing in the same `send-history.jsonl` the CLI
writes, with no second APNs client anywhere.

One `Sender` holds **one** `ApnsClient` (one pooled HTTP/2 connection, TLS
negotiated once) and **one** `ProviderTokenSigner` (JWT minted once, reused for
45 min, re-signed under a lock only when stale). So a tight loop does not
renegotiate TLS per send and cannot trip `TooManyProviderTokenUpdates` by
re-minting the provider token too often — as long as you reuse the Sender
instead of constructing one per send. (The CLI constructs one per invocation,
which is why a subprocess-per-send loop is the wrong way to drive this.)

Usage:

    from apns_harness.api import Sender
    from apns_harness.payloads import example_payload

    with Sender(environment="sandbox") as s:
        for i in range(200):
            resp = s.send(
                type="la-update",
                token=per_activity_token,
                payload=example_payload("la-update"),
                collapse_id="ramp",
                headline=f"ramp {i}",
            )
            print(resp.status_code, resp.reason)
            time.sleep(interval)

`send()` returns the parsed `ApnsResponse` (`.status_code`, `.reason`, `.ok`,
`.apns_id`, `.apns_unique_id`, `.timestamp`, `.hint()`, `.as_dict()`).
"""

from __future__ import annotations

import copy
import time

from . import config, history
from .client import ApnsClient, ApnsResponse, BuiltRequest
from .payloads import (
    PUSH_TYPES,
    inject_timestamp,
    refresh_updated_at,
    validate,
)


class Sender:
    """Reusable APNs sender with history logging. Not thread-safe for concurrent
    `send()` calls on one instance; fine for a single-threaded loop."""

    def __init__(
        self,
        *,
        environment: str = "sandbox",
        cfg: config.ApnsConfig | None = None,
        log: bool = True,
        timeout: float = 15.0,
    ) -> None:
        self.cfg = cfg or config.load()
        self.environment = environment
        self.log_enabled = log
        self.client = ApnsClient(self.cfg, environment=environment, timeout=timeout)
        self.sent = 0

    # ------------------------------------------------------------------ lifecycle
    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Sender":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def provider_token_refreshes(self) -> int:
        """How many times the JWT has actually been (re)signed — watch this stay
        low across a long ramp."""
        return self.client.signer.refreshes

    # ----------------------------------------------------------------------- send
    def send(
        self,
        *,
        type: str,
        token: str,
        payload: dict,
        headline: str | None = None,
        collapse_id: str | None = None,
        priority: int | None = None,
        expiration: int | None = None,
        ttl: int | None = None,
        dismissal_in: int | None = None,
        apns_id: str | None = None,
        topic_override: str | None = None,
        refresh_la_fields: bool = True,
        validate_payload: bool = True,
        force_token_refresh: bool = False,
        log: bool | None = None,
        extra_log: dict | None = None,
    ) -> ApnsResponse:
        """Send one push. `payload` is deep-copied, never mutated in place.

        For `la-*` types, `refresh_la_fields` (default on) injects a fresh
        `aps.timestamp` and, if `content-state.updatedAt` is a string, refreshes
        it to now (numeric Unix epoch seconds) — same behaviour as the CLI.
        `headline`, when given,
        overwrites `aps.content-state.headline` (convenience for labelled ramps).
        """
        req, resp, _ = self.send_detailed(
            type=type, token=token, payload=payload, headline=headline,
            collapse_id=collapse_id, priority=priority, expiration=expiration,
            ttl=ttl, dismissal_in=dismissal_in, apns_id=apns_id,
            topic_override=topic_override, refresh_la_fields=refresh_la_fields,
            validate_payload=validate_payload, force_token_refresh=force_token_refresh,
            log=log, extra_log=extra_log,
        )
        return resp

    def send_detailed(
        self,
        *,
        type: str,
        token: str,
        payload: dict,
        headline: str | None = None,
        collapse_id: str | None = None,
        priority: int | None = None,
        expiration: int | None = None,
        ttl: int | None = None,
        dismissal_in: int | None = None,
        apns_id: str | None = None,
        topic_override: str | None = None,
        refresh_la_fields: bool = True,
        validate_payload: bool = True,
        force_token_refresh: bool = False,
        log: bool | None = None,
        extra_log: dict | None = None,
    ) -> tuple[BuiltRequest, ApnsResponse, dict]:
        """Like `send()` but also returns the `BuiltRequest` and the history
        record (written or not). Useful when the caller wants the exact headers
        or the redacted request for its own notes."""
        if type not in PUSH_TYPES:
            raise KeyError(f"unknown push type {type!r}; one of {sorted(PUSH_TYPES)}")
        push_type = PUSH_TYPES[type]
        payload = copy.deepcopy(payload)

        if headline is not None:
            cs = payload.setdefault("aps", {}).setdefault("content-state", {})
            cs["headline"] = headline

        if push_type.topic_kind == "liveactivity" and refresh_la_fields:
            inject_timestamp(payload)
            refresh_updated_at(payload)
            if dismissal_in is not None:
                payload["aps"]["dismissal-date"] = int(time.time()) + dismissal_in

        if validate_payload:
            validate(payload, push_type)  # raises PayloadError

        if ttl is not None:
            expiration = int(time.time()) + ttl

        req, resp = self.client.send(
            push_type=push_type,
            device_token=token,
            payload=payload,
            priority=priority,
            collapse_id=collapse_id,
            expiration=expiration,
            apns_id=apns_id,
            topic_override=topic_override,
            force_token_refresh=force_token_refresh,
        )
        self.sent += 1

        record = {
            "type": type,
            "environment": self.environment,
            "device_token_redacted": history.redact_token(token),
            "request": {"url": req.url, "headers": req.redacted_headers()},
            "payload": payload,
            "response": resp.as_dict(),
            "source": "api.Sender",
        }
        if extra_log:
            record["meta"] = extra_log
        should_log = self.log_enabled if log is None else log
        if should_log:
            history.record(record)
        return req, resp, record


def send_once(
    *,
    type: str,
    token: str,
    payload: dict,
    environment: str = "sandbox",
    **kwargs: object,
) -> ApnsResponse:
    """One-shot convenience: build a Sender, send, close. Do NOT call this in a
    loop — it re-mints the provider token every call. Use `Sender` for loops."""
    with Sender(environment=environment) as s:
        return s.send(type=type, token=token, payload=payload, **kwargs)  # type: ignore[arg-type]
