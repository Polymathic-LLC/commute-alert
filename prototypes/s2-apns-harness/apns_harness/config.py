"""Credential loading for the APNs harness.

Canonical layout (agreed with the derisk orchestrator so the human can drop
credentials in without a round trip):

    prototypes/s2-apns-harness/.secrets/AuthKey_<KEYID>.p8
    prototypes/s2-apns-harness/.secrets/apns.env   # APNS_KEY_ID / APNS_TEAM_ID / APNS_BUNDLE_ID

apns.env always wins. `APNS_TEAM_ID` and `APNS_BUNDLE_ID` fall back to the
S3-probe constants in `defaults.py` when absent — with a loud warning — so a
missing env var becomes a visible warning, never a silent wrong-topic push
(the exact failure mode the S2 brief flags). `APNS_KEY_ID` has no fallback: it
is minted with the .p8 and only the human has it, so it stays blocking.

`--dry-run` skips loading entirely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import defaults, paths

PROTOTYPE_ROOT = paths.local_prototype_root()

# Test hooks: when set (to a Path), these win over the runtime resolution in
# `paths`. Production leaves them None so credentials are found in the main
# checkout even when this code runs inside a git worktree.
SECRETS_DIR: Path | None = None
ENV_FILE: Path | None = None


def _secrets_dir() -> Path:
    return SECRETS_DIR if SECRETS_DIR is not None else paths.secrets_dir()


def _env_file() -> Path:
    return ENV_FILE if ENV_FILE is not None else _secrets_dir() / "apns.env"


REQUIRED_ENV_KEYS = ("APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID")
# Keys that stay blocking when missing (no safe default exists).
BLOCKING_ENV_KEYS = ("APNS_KEY_ID",)
ENV_DEFAULTS = {
    "APNS_TEAM_ID": defaults.TEAM_ID,
    "APNS_BUNDLE_ID": defaults.APP_BUNDLE_ID,
}


class CredentialsMissing(Exception):
    """Raised when the .p8 key or a blocking env value is not present."""


@dataclass(frozen=True)
class ApnsConfig:
    key_id: str
    team_id: str
    bundle_id: str
    p8_path: Path
    p8_pem: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def liveactivity_topic(self) -> str:
        return f"{self.bundle_id}.push-type.liveactivity"


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal dotenv parser: KEY=VALUE lines, `#` comments, optional quotes."""
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            values[key] = val
    return values


def _merged_env(env_overrides: dict[str, str] | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = _env_file()
    if env_file.is_file():
        env.update(_parse_env_file(env_file))
    for k in REQUIRED_ENV_KEYS:  # process env wins over the file
        if os.environ.get(k):
            env[k] = os.environ[k]
    if env_overrides:
        env.update({k: v for k, v in env_overrides.items() if v})
    return env


def _resolve_p8(secrets_dir: Path, key_id: str) -> Path:
    """Prefer AuthKey_<KEYID>.p8; fall back to a lone *.p8 in .secrets/."""
    named = secrets_dir / f"AuthKey_{key_id}.p8"
    if named.is_file():
        return named
    candidates = sorted(secrets_dir.glob("*.p8"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise CredentialsMissing(
            f"No .p8 key found. Expected {named} "
            f"(or a single *.p8 file in {secrets_dir}/)."
        )
    raise CredentialsMissing(
        f"Multiple .p8 files in {secrets_dir}/ and none named AuthKey_{key_id}.p8: "
        + ", ".join(p.name for p in candidates)
    )


def describe_state() -> list[str]:
    """Human-readable checklist of what is / isn't present. Used by `doctor`."""
    secrets_dir = _secrets_dir()
    env_file = _env_file()
    lines: list[str] = []
    if paths.IN_WORKTREE:
        lines.append("(running in a git worktree — credentials are read from the main checkout)")
    lines.append(f"secrets dir : {secrets_dir}  [{'present' if secrets_dir.is_dir() else 'MISSING'}]")
    env = _merged_env()
    lines.append(f"apns.env    : {env_file}  [{'present' if env_file.is_file() else 'MISSING'}]")
    for k in REQUIRED_ENV_KEYS:
        v = env.get(k, "")
        if v:
            lines.append(f"  {k:<15}: (set) {v}")
        elif k in ENV_DEFAULTS:
            lines.append(f"  {k:<15}: unset — would fall back to {ENV_DEFAULTS[k]!r} (with warning)")
        else:
            lines.append(f"  {k:<15}: MISSING (blocking — no default)")
    try:
        if secrets_dir.is_dir():
            p8 = _resolve_p8(secrets_dir, env.get("APNS_KEY_ID", ""))
            lines.append(f"p8 key      : {p8}  [present]")
        else:
            lines.append("p8 key      : not checked (secrets dir missing)")
    except CredentialsMissing as exc:
        lines.append(f"p8 key      : {exc}")
    return lines


def load(*, env_overrides: dict[str, str] | None = None) -> ApnsConfig:
    """Load and validate credentials. Raise `CredentialsMissing` if a blocking
    value or the .p8 is absent. Non-blocking gaps become `.warnings`."""
    env = _merged_env(env_overrides)
    warnings: list[str] = []
    secrets_dir = _secrets_dir()
    env_file = _env_file()

    blocking_missing = [k for k in BLOCKING_ENV_KEYS if not env.get(k)]
    if blocking_missing:
        raise CredentialsMissing(
            "APNs credentials incomplete.\n"
            f"  Missing (blocking): {', '.join(blocking_missing)}\n"
            f"  Fill in: {env_file}\n"
            "  Format :\n"
            "    APNS_KEY_ID=ABC123DEFG        # from the .p8 you download\n"
            f"    APNS_TEAM_ID={defaults.TEAM_ID}         # optional; this is the default\n"
            f"    APNS_BUNDLE_ID={defaults.APP_BUNDLE_ID}\n"
            f"  And drop the key at: {secrets_dir}/AuthKey_<KEYID>.p8\n"
            "  (Or run with --dry-run to exercise the tool without credentials.)"
        )

    for k, dflt in ENV_DEFAULTS.items():
        if not env.get(k):
            env[k] = dflt
            warnings.append(
                f"{k} not set in {env_file.name} — using default {dflt!r} "
                "(S3-probe value; confirm it matches S3's Xcode project)"
            )

    if not secrets_dir.is_dir():
        raise CredentialsMissing(f"Secrets dir does not exist: {secrets_dir}")

    p8_path = _resolve_p8(secrets_dir, env["APNS_KEY_ID"])
    p8_pem = p8_path.read_text()
    if "BEGIN PRIVATE KEY" not in p8_pem:
        raise CredentialsMissing(
            f"{p8_path} does not look like a PKCS#8 .p8 key "
            "(no 'BEGIN PRIVATE KEY' header)."
        )

    if env["APNS_BUNDLE_ID"] == defaults.PRODUCTION_BUNDLE_ID:
        warnings.append(
            f"APNS_BUNDLE_ID is the PRODUCTION id {defaults.PRODUCTION_BUNDLE_ID!r}; "
            "the S3 probe uses a distinct throwaway id"
        )

    return ApnsConfig(
        key_id=env["APNS_KEY_ID"].strip(),
        team_id=env["APNS_TEAM_ID"].strip(),
        bundle_id=env["APNS_BUNDLE_ID"].strip(),
        p8_path=p8_path,
        p8_pem=p8_pem,
        warnings=tuple(warnings),
    )
