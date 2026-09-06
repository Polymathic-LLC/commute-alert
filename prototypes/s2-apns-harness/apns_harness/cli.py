"""CLI for the APNs push harness.

    python -m apns_harness doctor
    python -m apns_harness example la-start
    python -m apns_harness send --type la-start --token <hex> --payload payloads/live-activity-start.json
    python -m apns_harness send --type alert  --token <hex> --payload payloads/alert.json --env sandbox
    python -m apns_harness history -n 20
    python -m apns_harness jwt            # decode the provider token we would send

`send` without credentials exits cleanly with instructions. `send --dry-run`
builds and prints the exact request (URL, headers, body, equivalent curl)
without needing credentials or network.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import config, history, tokens
from .client import ApnsClient, build_request
from .jwt_auth import ProviderTokenSigner, decode_unverified
from .payloads import (
    PUSH_TYPES,
    PayloadError,
    example_payload,
    inject_timestamp,
    parse_payload,
    validate,
)

PROTOTYPE_ROOT = Path(__file__).resolve().parent.parent


def _eprint(*a: object) -> None:
    print(*a, file=sys.stderr)


# --------------------------------------------------------------------------- doctor
def cmd_doctor(args: argparse.Namespace) -> int:
    print("APNs harness — credential check\n")
    for line in config.describe_state():
        print("  " + line)
    print()
    print(tokens.describe())
    print()
    try:
        cfg = config.load()
    except config.CredentialsMissing as exc:
        print("RESULT: not ready for live sends.\n")
        print(str(exc))
        print("\n--dry-run works without any of the above.")
        return 1
    for w in cfg.warnings:
        print(f"  WARNING: {w}")
    print("RESULT: credentials present.")
    print(f"  team_id            : {cfg.team_id}")
    print(f"  key_id             : {cfg.key_id}")
    print(f"  bundle_id          : {cfg.bundle_id}")
    print(f"  liveactivity topic : {cfg.liveactivity_topic}")
    print(f"  p8 key             : {cfg.p8_path}")
    try:
        signer = ProviderTokenSigner(key_id=cfg.key_id, team_id=cfg.team_id, p8_pem=cfg.p8_pem)
        tok = signer.token()
        print("  provider JWT       : signed OK "
              f"(len {len(tok.value)}, iat {tok.issued_at})")
    except Exception as exc:  # noqa: BLE001 — surface any signing failure plainly
        print(f"  provider JWT       : FAILED TO SIGN — {exc!r}")
        return 1
    return 0


# -------------------------------------------------------------------------- example
def cmd_example(args: argparse.Namespace) -> int:
    payload = example_payload(args.type)
    text = json.dumps(payload, indent=2)
    if args.write:
        dest = Path(args.write)
        dest.write_text(text + "\n")
        print(f"wrote {dest}")
    else:
        print(text)
    return 0


# -------------------------------------------------------------------------- history
def cmd_history(args: argparse.Namespace) -> int:
    rows = history.tail(args.n)
    if not rows:
        print(f"no send history at {history.HISTORY_PATH}")
        return 0
    for r in rows:
        resp = r.get("response", {})
        print(
            f"{r.get('logged_at_iso','?')}  {r.get('type','?'):<10} "
            f"env={r.get('environment','?'):<7} "
            f"http={resp.get('status_code','?')} "
            f"reason={resp.get('reason') or '-'} "
            f"apns-id={resp.get('apns_id') or '-'} "
            f"token={r.get('device_token_redacted','?')}"
        )
    return 0


# ------------------------------------------------------------------------------ jwt
def cmd_jwt(args: argparse.Namespace) -> int:
    try:
        cfg = config.load()
    except config.CredentialsMissing as exc:
        _eprint(str(exc))
        return 1
    signer = ProviderTokenSigner(key_id=cfg.key_id, team_id=cfg.team_id, p8_pem=cfg.p8_pem)
    tok = signer.token()
    info = decode_unverified(tok.value)
    print(json.dumps({"token_preview": tok.value[:24] + "…", **info}, indent=2))
    return 0


# ----------------------------------------------------------------------------- send
def _load_payload(args: argparse.Namespace) -> dict:
    if args.payload:
        path = Path(args.payload)
        if not path.is_file():
            raise SystemExit(f"payload file not found: {path}")
        try:
            return parse_payload(path)
        except PayloadError as exc:
            raise SystemExit(str(exc))
    if args.example:
        return example_payload(args.type)
    raise SystemExit("send needs --payload <file> or --example")


def _resolve_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()
    if args.token_file:
        return Path(args.token_file).read_text().strip()
    tokens_file = Path(args.tokens_file) if args.tokens_file else None
    if args.token_role:
        try:
            return tokens.resolve(args.token_role, path=tokens_file)
        except tokens.TokenFileError as exc:
            raise SystemExit(str(exc))
    # Sensible default: la-* sends use the matching Live Activity token role.
    implied = {"la-start": "pts", "la-update": "activity", "la-end": "activity",
               "alert": "device", "background": "device"}.get(args.type)
    if implied:
        try:
            tok = tokens.resolve(implied, path=tokens_file)
            _eprint(f"  (using {implied!r} token from {tokens_file or tokens.tokens_path()})")
            return tok
        except tokens.TokenFileError as exc:
            raise SystemExit(
                f"No token given and could not auto-resolve role {implied!r}:\n{exc}\n"
                "Pass --token <hex>, --token-file <path>, or --token-role."
            )
    raise SystemExit("send needs --token <hex>, --token-file <path>, or --token-role")


def cmd_send(args: argparse.Namespace) -> int:
    push_type = PUSH_TYPES[args.type]
    payload = _load_payload(args)
    try:
        token = _resolve_token(args)
    except SystemExit:
        if not args.dry_run:
            raise
        token = "<device-token-placeholder>"
        _eprint("  (dry-run: no token resolved — using placeholder)")

    # Live Activity ordering: stamp a fresh aps.timestamp unless one was set.
    if push_type.topic_kind == "liveactivity":
        if inject_timestamp(payload):
            _eprint("  (injected aps.timestamp = now)")
        if args.dismissal_in is not None:
            payload["aps"]["dismissal-date"] = int(time.time()) + args.dismissal_in
        elif args.dismissal_date is not None:
            payload["aps"]["dismissal-date"] = args.dismissal_date

    try:
        warnings = validate(payload, push_type)
    except PayloadError as exc:
        _eprint(f"payload invalid for --type {args.type}: {exc}")
        return 2
    for w in warnings:
        _eprint(f"  warn: {w}")

    expiration = args.expiration
    if args.ttl is not None:
        expiration = int(time.time()) + args.ttl

    if args.dry_run:
        req = build_request(
            cfg=None if args.no_creds else _safe_cfg(),
            push_type=push_type,
            device_token=token,
            payload=payload,
            environment=args.env,
            priority=args.priority,
            collapse_id=args.collapse_id,
            expiration=expiration,
            topic_override=args.topic,
        )
        print("DRY RUN — no request sent\n")
        print(f"{req.method} {req.url}")
        for k, v in req.redacted_headers().items():
            print(f"  {k}: {v}")
        print("\nbody:")
        print(json.dumps(req.json_body, indent=2))
        print("\nequivalent curl:\n" + req.curl())
        return 0

    try:
        cfg = config.load()
    except config.CredentialsMissing as exc:
        _eprint("Cannot send: APNs credentials are not in place.\n")
        _eprint(str(exc))
        return 3
    for w in cfg.warnings:
        _eprint(f"  WARNING: {w}")

    with ApnsClient(cfg, environment=args.env) as client:
        req, resp = client.send(
            push_type=push_type,
            device_token=token,
            payload=payload,
            priority=args.priority,
            collapse_id=args.collapse_id,
            expiration=expiration,
            topic_override=args.topic,
            force_token_refresh=args.force_token_refresh,
        )

    entry = {
        "type": args.type,
        "environment": args.env,
        "device_token_redacted": history.redact_token(token),
        "request": {
            "url": req.url,
            "headers": req.redacted_headers(),
        },
        "payload": payload,
        "response": resp.as_dict(),
    }
    log_path = history.record(entry)

    print(f"HTTP {resp.status_code}  {'OK' if resp.ok else 'ERROR'}")
    print(f"  apns-id        : {resp.apns_id}")
    print(f"  apns-unique-id : {resp.apns_unique_id}")
    print(f"  reason         : {resp.reason or '-'}")
    if resp.timestamp:
        print(f"  timestamp      : {resp.timestamp}")
    if resp.hint():
        print(f"  hint           : {resp.hint()}")
    if resp.raw_body.strip():
        print(f"  raw body       : {resp.raw_body.strip()}")
    print(f"  logged         : {log_path}")
    return 0 if resp.ok else 4


def _safe_cfg():
    try:
        return config.load()
    except config.CredentialsMissing:
        return None


# ---------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="apns_harness", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check credential state and try signing a JWT").set_defaults(
        func=cmd_doctor
    )

    ex = sub.add_parser("example", help="print an example payload for a push type")
    ex.add_argument("type", choices=sorted(PUSH_TYPES))
    ex.add_argument("--write", help="write to this path instead of stdout")
    ex.set_defaults(func=cmd_example)

    hi = sub.add_parser("history", help="show recent send history")
    hi.add_argument("-n", type=int, default=10)
    hi.set_defaults(func=cmd_history)

    sub.add_parser("jwt", help="decode the provider token we would send").set_defaults(func=cmd_jwt)

    s = sub.add_parser("send", help="send one push")
    s.add_argument("--type", required=True, choices=sorted(PUSH_TYPES))
    s.add_argument("--token", help="hex device or Live Activity token")
    s.add_argument("--token-file", help="file containing the token")
    s.add_argument(
        "--token-role",
        choices=sorted(tokens.ROLE_ALIASES),
        help="read the token from S3's tokens.md by role "
        "(pts=push-to-start, activity=per-activity, device=plain APNs). "
        "Defaults per --type when omitted.",
    )
    s.add_argument(
        "--tokens-file",
        help="explicit path to S3's tokens.md (overrides auto-discovery / $S3_TOKENS_FILE)",
    )
    s.add_argument("--payload", help="JSON payload file")
    s.add_argument("--example", action="store_true", help="use the built-in example payload")
    s.add_argument("--env", default="sandbox", choices=["sandbox", "prod"])
    s.add_argument("--priority", type=int, help="apns-priority override (10 or 5)")
    s.add_argument("--collapse-id", help="apns-collapse-id (<=64 bytes)")
    s.add_argument("--expiration", type=int, help="apns-expiration (unix seconds; 0 = now-or-never)")
    s.add_argument("--ttl", type=int, help="seconds from now; sets apns-expiration")
    s.add_argument("--dismissal-in", type=int, help="la-end: dismissal-date = now + N seconds")
    s.add_argument("--dismissal-date", type=int, help="la-end: dismissal-date (unix seconds)")
    s.add_argument("--topic", help="apns-topic override (advanced / debugging)")
    s.add_argument("--force-token-refresh", action="store_true", help="mint a fresh provider JWT")
    s.add_argument("--dry-run", action="store_true", help="print the request; send nothing")
    s.add_argument(
        "--no-creds",
        action="store_true",
        help="with --dry-run, don't even read credentials (show placeholder topic)",
    )
    s.set_defaults(func=cmd_send)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
