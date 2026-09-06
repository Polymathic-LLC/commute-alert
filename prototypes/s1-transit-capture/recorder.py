#!/usr/bin/env python3
"""
MBTA stream recorder — prototype for S1 (see DERISKING.md).

Captures, for each configured target:
  - the /predictions SSE stream (primary artifact)
  - periodic /schedules, /vehicles, /alerts snapshots

Everything is written as newline-delimited JSON with local receive
timestamps, one file per (target, stream, UTC day). Disconnects,
reconnects, and detected gaps are logged explicitly to a connection
log per target — a capture with silent gaps is not usable, so nothing
here is allowed to fail quietly.

This is throwaway prototype code (see DERISKING.md: "Nothing here is
production code"). It intentionally does not share anything with
backend/app.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

MBTA_BASE_URL = "https://api-v3.mbta.com"

# SSE docs (docs/mbta-api.md): reconnect with exponential backoff,
# 1s/2s/4s/... capped at 60s.
RECONNECT_BACKOFF_INITIAL_S = 1.0
RECONNECT_BACKOFF_MAX_S = 60.0

# If no SSE event (including periodic `reset`) arrives within this window,
# treat the connection as silently dead and force a reconnect. MBTA's own
# subway update cadence is ~10-25s and commuter rail ~30-60s (docs/mbta-api.md),
# so 120s is well past normal quiet periods for either.
SSE_WATCHDOG_TIMEOUT_S = 120.0

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("recorder")


def load_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE .env parser — no external dependency needed for
    a handful of secrets. Ignores blank lines and '#' comments."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_day(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


@dataclasses.dataclass(frozen=True)
class Target:
    name: str
    route: str
    stop: str
    route_type: str  # "commuter_rail" | "rapid_transit" — drives staleness threshold
    staleness_threshold_s: int


TARGETS = [
    Target(
        name="cr-worcester-boston-landing",
        route="CR-Worcester",
        stop="place-WML-0091",  # Boston Landing (parent station, covers both directions)
        route_type="commuter_rail",
        staleness_threshold_s=300,
    ),
    Target(
        # Secondary rapid-transit target, chosen per DERISKING.md step:
        # Red Line at Harvard. Rationale (see FINDINGS.md): high frequency,
        # both directions through one parent stop, and a mid-line stop
        # rather than a terminus — a terminus would show `AT_TERMINAL`
        # for every prediction and never exercise the mid-trip staleness
        # signal this secondary target exists to test. Captured at the
        # SAME fidelity (SSE + poll cadence) as the commuter-rail target —
        # per S1a, update_type/arrival_uncertainty/schedule_relationship
        # are frequently null on commuter rail, making this stop the main
        # source for those signals. See FINDINGS.md.
        #
        # Note: `update_type` values observed live are UPPERCASE
        # (MID_TRIP, AT_TERMINAL, REVERSE_TRIP) — docs/mbta-api.md shows
        # lowercase and omits REVERSE_TRIP. Not relevant to this recorder
        # (it records raw JSON, doesn't branch on these values), but
        # matters for anyone reading captured data. See FINDINGS.md.
        name="red-line-harvard",
        route="Red",
        stop="place-harsq",
        route_type="rapid_transit",
        staleness_threshold_s=90,
    ),
]

# Poll intervals. Deliberately modest — see FINDINGS.md for the rate-limit
# budget these were chosen against.
VEHICLES_POLL_INTERVAL_S = 30
SCHEDULES_POLL_INTERVAL_S = 600
ALERTS_POLL_INTERVAL_S = 300


class NdjsonWriter:
    """Append-only NDJSON writer, one file per UTC day, reopened on rollover."""

    def __init__(self, base_dir: Path, target_name: str, stream: str):
        self.dir = base_dir / target_name / stream
        self.dir.mkdir(parents=True, exist_ok=True)
        self._day: Optional[str] = None
        self._fh = None

    def _ensure_open(self) -> None:
        day = utc_day()
        if day != self._day:
            if self._fh is not None:
                self._fh.close()
            self._day = day
            path = self.dir / f"{day}.ndjson"
            self._fh = path.open("a", buffering=1, encoding="utf-8")

    def write(self, record: dict) -> None:
        self._ensure_open()
        self._fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class ConnectionLog:
    """Shared append-only log of connect/disconnect/gap events per target."""

    def __init__(self, base_dir: Path, target_name: str):
        self.dir = base_dir / target_name / "meta"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "connection_log.ndjson"

    def log(self, **fields: Any) -> None:
        record = {"ts": now_iso(), **fields}
        with self.path.open("a", buffering=1, encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        log.info("connlog %s: %s", self.path.parent.parent.name, record)


def parse_sse_events(raw_lines: list[str]) -> list[dict]:
    """Parse one SSE 'block' (lines between blank-line separators) into
    zero or more logical events. MBTA sends one JSON payload per event,
    on one or more `data:` lines."""
    event_type = None
    event_id = None
    data_lines: list[str] = []
    for line in raw_lines:
        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
        elif line.startswith("id:"):
            event_id = line[len("id:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
        elif line.startswith(":"):
            continue  # comment/heartbeat
    if not data_lines:
        return []
    data_str = "\n".join(data_lines)
    try:
        payload = json.loads(data_str)
    except json.JSONDecodeError:
        log.warning("failed to parse SSE data block (event=%s): %r", event_type, data_str[:200])
        return []
    return [{"event": event_type, "id": event_id, "data": payload}]


async def predictions_sse_loop(
    client: httpx.AsyncClient,
    target: Target,
    writer: NdjsonWriter,
    connlog: ConnectionLog,
    api_key: Optional[str],
) -> None:
    url = f"{MBTA_BASE_URL}/predictions"
    params = {"filter[route]": target.route, "filter[stop]": target.stop}
    last_event_id: Optional[str] = None
    backoff = RECONNECT_BACKOFF_INITIAL_S
    connlog.log(stream="predictions", type="startup", detail=params)

    while True:
        headers = {"Accept": "text/event-stream"}
        if api_key:
            headers["x-api-key"] = api_key
        if last_event_id:
            headers["Last-Event-Id"] = last_event_id

        connect_started_at = datetime.now(timezone.utc)
        events_this_connection = 0
        try:
            async with client.stream(
                "GET", url, params=params, headers=headers, timeout=httpx.Timeout(SSE_WATCHDOG_TIMEOUT_S, connect=30.0)
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    connlog.log(
                        stream="predictions",
                        type="connect_error",
                        status=resp.status_code,
                        detail=body[:500].decode(errors="replace"),
                    )
                    raise RuntimeError(f"predictions SSE returned {resp.status_code}")

                connlog.log(stream="predictions", type="connected", resumed_from=last_event_id)
                backoff = RECONNECT_BACKOFF_INITIAL_S  # reset on successful connect

                block: list[str] = []
                last_activity = datetime.now(timezone.utc)

                async def watchdog():
                    nonlocal last_activity
                    while True:
                        await asyncio.sleep(5)
                        idle = (datetime.now(timezone.utc) - last_activity).total_seconds()
                        if idle > SSE_WATCHDOG_TIMEOUT_S:
                            raise TimeoutError(f"no SSE activity for {idle:.0f}s")

                watchdog_task = asyncio.create_task(watchdog())
                try:
                    async for line in resp.aiter_lines():
                        last_activity = datetime.now(timezone.utc)
                        if line == "":
                            if block:
                                for evt in parse_sse_events(block):
                                    received_at = now_iso()
                                    writer.write({"received_at": received_at, **evt})
                                    if evt.get("id"):
                                        last_event_id = evt["id"]
                                    events_this_connection += 1
                                block = []
                        else:
                            block.append(line)
                finally:
                    watchdog_task.cancel()
                    try:
                        await watchdog_task
                    except (asyncio.CancelledError, TimeoutError):
                        pass

            # Server closed the stream cleanly (unexpected but not an error path we crash on).
            gap_started = datetime.now(timezone.utc)
            connlog.log(
                stream="predictions",
                type="disconnect",
                reason="stream_closed_by_server",
                events_received=events_this_connection,
                connection_duration_s=(gap_started - connect_started_at).total_seconds(),
            )

        except (httpx.HTTPError, TimeoutError, RuntimeError, OSError) as exc:
            gap_started = datetime.now(timezone.utc)
            connlog.log(
                stream="predictions",
                type="disconnect",
                reason=f"{type(exc).__name__}: {exc}",
                events_received=events_this_connection,
                connection_duration_s=(gap_started - connect_started_at).total_seconds(),
            )

        connlog.log(stream="predictions", type="reconnect_wait", backoff_s=backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX_S)


async def poll_loop(
    client: httpx.AsyncClient,
    target: Target,
    endpoint: str,
    params: dict,
    interval_s: int,
    writer: NdjsonWriter,
    connlog: ConnectionLog,
    api_key: Optional[str],
) -> None:
    url = f"{MBTA_BASE_URL}/{endpoint}"
    while True:
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key
        request_params = dict(params)
        if endpoint == "schedules":
            request_params["filter[date]"] = utc_day()
        received_at = now_iso()
        try:
            resp = await client.get(url, params=request_params, headers=headers, timeout=30.0)
            if resp.status_code == 200:
                writer.write({"received_at": received_at, "status": resp.status_code, "data": resp.json()})
            else:
                writer.write(
                    {
                        "received_at": received_at,
                        "status": resp.status_code,
                        "error": resp.text[:1000],
                    }
                )
                connlog.log(stream=endpoint, type="poll_error", status=resp.status_code, detail=resp.text[:500])
        except httpx.HTTPError as exc:
            writer.write({"received_at": received_at, "error": f"{type(exc).__name__}: {exc}"})
            connlog.log(stream=endpoint, type="poll_error", detail=str(exc))
        await asyncio.sleep(interval_s)


async def supervised(coro_factory, name: str, connlog: ConnectionLog):
    """Run a task forever; if it somehow raises past its own internal
    recovery, log it and restart after a short delay rather than taking
    the whole recorder down."""
    while True:
        try:
            await coro_factory()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — top-level safety net, by design
            connlog.log(stream=name, type="task_crashed", detail=f"{type(exc).__name__}: {exc}")
            log.exception("task %s crashed, restarting in 10s", name)
            await asyncio.sleep(10)


async def run(out_dir: Path, api_key: Optional[str], targets: list[Target]) -> None:
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = []
        for target in targets:
            connlog = ConnectionLog(out_dir, target.name)

            pred_writer = NdjsonWriter(out_dir, target.name, "predictions")
            tasks.append(
                asyncio.create_task(
                    supervised(
                        lambda t=target, w=pred_writer, c=connlog: predictions_sse_loop(client, t, w, c, api_key),
                        f"{target.name}/predictions",
                        connlog,
                    )
                )
            )

            for endpoint, interval, params in [
                ("schedules", SCHEDULES_POLL_INTERVAL_S, {"filter[route]": target.route, "filter[stop]": target.stop}),
                ("vehicles", VEHICLES_POLL_INTERVAL_S, {"filter[route]": target.route}),
                ("alerts", ALERTS_POLL_INTERVAL_S, {"filter[route]": target.route}),
            ]:
                writer = NdjsonWriter(out_dir, target.name, endpoint)
                tasks.append(
                    asyncio.create_task(
                        supervised(
                            lambda t=target, e=endpoint, p=params, i=interval, w=writer, c=connlog: poll_loop(
                                client, t, e, p, i, w, c, api_key
                            ),
                            f"{target.name}/{endpoint}",
                            connlog,
                        )
                    )
                )

        stop_event = asyncio.Event()

        def _handle_signal(sig_name: str):
            log.info("received %s, shutting down", sig_name)
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _handle_signal, sig.name)

        await stop_event.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default=os.environ.get("RECORDER_OUT_DIR", "./data"),
        help="Output directory for captured NDJSON (default: ./data, or $RECORDER_OUT_DIR)",
    )
    secrets_env = load_env_file(Path(__file__).parent / ".secrets" / "mbta.env")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MBTA_API_KEY") or secrets_env.get("MBTA_API_KEY"),
        help=(
            "MBTA v3 API key. Checked in order: --api-key, $MBTA_API_KEY, "
            "./.secrets/mbta.env (MBTA_API_KEY=...). Optional but strongly "
            "recommended for a long run."
        ),
    )
    parser.add_argument(
        "--dry-run-seconds",
        type=int,
        default=0,
        help="If set, run for this many seconds then exit (for local testing).",
    )
    args = parser.parse_args()

    if not args.api_key:
        log.warning(
            "no MBTA API key set (--api-key or $MBTA_API_KEY) — running unauthenticated. "
            "See FINDINGS.md for why this matters for a multi-day run."
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    async def _main():
        if args.dry_run_seconds:
            try:
                await asyncio.wait_for(run(out_dir, args.api_key, TARGETS), timeout=args.dry_run_seconds)
            except asyncio.TimeoutError:
                log.info("dry run complete (%ss)", args.dry_run_seconds)
        else:
            await run(out_dir, args.api_key, TARGETS)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
