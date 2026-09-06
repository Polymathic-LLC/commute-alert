"""Read device tokens from S3's shared file.

S3 has the human paste three tokens into `prototypes/s3-apple-setup/tokens.md`
(gitignored; template at `tokens.example.md`):

  - Live Activity push-to-start token   -> role "pts"
  - Live Activity per-activity token     -> role "activity"
  - Plain APNs device token              -> role "device"

The exact line format S3 uses is not locked yet, so this parser is deliberately
loose: it scans for a line mentioning the role (by any of several aliases) and
takes the first hex run of >= 32 chars on that line or the next non-empty line.
A markdown table row works; a `key: value` line works; a bullet works.

If parsing turns out to disagree with S3's format, that is a finding, not a
crash — `resolve()` raises `TokenFileError` with the file contents echoed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import paths

PROTOTYPE_ROOT = paths.local_prototype_root()


def _candidate_paths() -> list[Path]:
    """Where S3's tokens.md might live, most-specific first.

    S2 may run in an isolated git worktree while S3 runs in the main checkout
    (or its own worktree), so the sibling `prototypes/s3-apple-setup/` is not
    always reachable by a plain `..`. Check $S3_TOKENS_FILE, then the
    main-checkout path, then the worktree-local sibling.
    """
    cands: list[Path] = []
    env = os.environ.get("S3_TOKENS_FILE")
    if env:
        cands.append(Path(env).expanduser())
    cands.append(paths.MAIN_PROTOTYPE_ROOT.parent / "s3-apple-setup" / "tokens.md")
    cands.append(PROTOTYPE_ROOT.parent / "s3-apple-setup" / "tokens.md")
    # de-dup, keep order
    seen: set[Path] = set()
    out: list[Path] = []
    for c in cands:
        c = c.resolve()
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def tokens_path() -> Path:
    """First existing candidate, else the first candidate (for messaging)."""
    cands = _candidate_paths()
    for c in cands:
        if c.is_file():
            return c
    return cands[0]


TOKENS_PATH = tokens_path()

HEX_RUN = re.compile(r"\b([0-9a-fA-F]{32,})\b")

ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "pts": ("push-to-start", "push to start", "pushtostart", "push_to_start", "pts", "start token"),
    "activity": (
        "per-activity",
        "per activity",
        "per_activity",
        "activity token",
        "activity push token",
        "update token",
        "liveactivity token",
    ),
    "device": (
        "device token",
        "apns device",
        "plain apns",
        "standard apns",
        "push token (device)",
        "devicetoken",
    ),
}

ROLE_LABELS = {
    "pts": "Live Activity push-to-start",
    "activity": "Live Activity per-activity",
    "device": "plain APNs device",
}


class TokenFileError(Exception):
    pass


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _extract_after(lines: list[str], idx: int) -> str | None:
    m = HEX_RUN.search(lines[idx])
    if m:
        return m.group(1)
    for j in range(idx + 1, min(idx + 3, len(lines))):
        if lines[j].strip():
            m = HEX_RUN.search(lines[j])
            if m:
                return m.group(1)
            break
    return None


def parse(text: str) -> dict[str, str]:
    """Return {role: token} for whatever roles are found."""
    lines = _lines(text)
    found: dict[str, str] = {}
    for role, aliases in ROLE_ALIASES.items():
        for i, line in enumerate(lines):
            low = line.lower()
            if any(a in low for a in aliases):
                tok = _extract_after(lines, i)
                if tok:
                    found[role] = tok
                    break
    return found


def resolve(role: str, *, path: Path | None = None) -> str:
    path = path or tokens_path()
    if role not in ROLE_ALIASES:
        raise TokenFileError(f"unknown token role {role!r}; expected one of {list(ROLE_ALIASES)}")
    if not path.is_file():
        raise TokenFileError(
            f"S3 token file not found: {path}\n"
            "  S3 populates it once the human pastes the three tokens from the device.\n"
            "  Until then, pass --token <hex> or --token-file explicitly."
        )
    text = path.read_text()
    found = parse(text)
    if role not in found:
        raise TokenFileError(
            f"Could not find the {ROLE_LABELS[role]} token in {path}.\n"
            f"  Looked for a line mentioning any of: {', '.join(ROLE_ALIASES[role])}\n"
            f"  Followed by a hex run of >=32 chars.\n"
            f"  Roles found: {sorted(found) or 'none'}\n"
            "  --- file contents ---\n"
            + "\n".join("  " + ln for ln in text.splitlines())
        )
    return found[role].strip()


def describe(path: Path | None = None) -> str:
    path = path or tokens_path()
    if not path.is_file():
        tried = "\n".join(f"    tried: {c}" for c in _candidate_paths())
        return f"S3 token file: {path}  [not yet present]\n{tried}"
    found = parse(path.read_text())
    bits = [f"S3 token file: {path}  [present]"]
    for role in ROLE_ALIASES:
        tok = found.get(role)
        if tok:
            bits.append(f"  {role:<9} ({ROLE_LABELS[role]}): {tok[:6]}…{tok[-4:]} (len {len(tok)})")
        else:
            bits.append(f"  {role:<9} ({ROLE_LABELS[role]}): not found")
    return "\n".join(bits)
