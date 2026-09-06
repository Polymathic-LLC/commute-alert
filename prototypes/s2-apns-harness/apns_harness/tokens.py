"""Read device tokens from S3's shared file.

S3 has the human paste three tokens into `prototypes/s3-apple-setup/tokens.md`
(gitignored; template `tokens.example.md`, referenced from S3's RUNBOOK.md).

S3's actual format, confirmed against its template: a `## Tokens` section with a
fenced code block, each token on the line AFTER its label:

    ```
    LIVE ACTIVITY push-to-start token:
    80a1b2c3...e8f

    LIVE ACTIVITY per-activity push token:
    11223344...eeff

    APNs device token (alert / background):
    ffeeddcc...2211
    ```

The parser handles: token on the same line OR a following line; blank lines and
code-fence lines between label and token; unfilled `<paste …>` placeholders
(these produce a LOUD `TokenFileError`, never a silent miss); and the fact that
the push-to-start label contains the substring "activity" (each label line is
assigned to exactly one role, most-specific first, so it cannot be mis-claimed).
Looser `key: value`, bullet, and table-row layouts still work as a fallback.
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
    # S3 may run in its own worktree and drop tokens.md there rather than in the
    # main checkout — check every worktree's copy, newest mtime first.
    repo_root = paths.MAIN_PROTOTYPE_ROOT.parent.parent
    wt_glob = sorted(
        repo_root.glob(".claude/worktrees/*/prototypes/s3-apple-setup/tokens.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    cands.extend(wt_glob)
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

HEX_RUN = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{32,})(?![0-9a-fA-F])")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
# How far past a label to look for its token (skipping blanks + fence lines).
_LOOKAHEAD = 6

# S3's verbatim labels (lowercased), highest precedence. Ordered most-specific
# first so the push-to-start label — which contains "activity" — is claimed by
# `pts` before `activity` ever sees it.
S3_EXACT_LABELS: tuple[tuple[str, str], ...] = (
    ("live activity push-to-start token", "pts"),
    ("apns device token (alert / background)", "device"),
    ("live activity per-activity push token", "activity"),
)

# Fallback fuzzy aliases for non-S3 layouts. Also ordered so `pts` wins ties.
ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "pts": ("push-to-start", "push to start", "pushtostart", "push_to_start", "pts token", "start token"),
    "activity": (
        "per-activity",
        "per activity",
        "per_activity",
        "activity push token",
        "activity token",
        "update token",
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

_PLACEHOLDER_HINTS = ("<paste", "<...", "paste —", "paste -", "todo", "tbd", "xxxx")


class TokenFileError(Exception):
    pass


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _looks_like_label(line: str) -> bool:
    low = line.lower()
    if any(lbl in low for lbl in (l for l, _ in S3_EXACT_LABELS)):
        return True
    return any(a in low for aliases in ROLE_ALIASES.values() for a in aliases)


def _extract_near(lines: list[str], idx: int, used_hex_lines: set[int]) -> tuple[str, int] | None:
    """Token on the label line itself, else on a following line — skipping
    blanks and code-fence markers, stopping at the next label line."""
    m = HEX_RUN.search(lines[idx])
    if m and idx not in used_hex_lines:
        return m.group(1), idx
    for j in range(idx + 1, min(idx + 1 + _LOOKAHEAD, len(lines))):
        raw = lines[j]
        if not raw.strip() or _FENCE_RE.match(raw):
            continue
        if j in used_hex_lines:
            continue
        m = HEX_RUN.search(raw)
        if m:
            return m.group(1), j
        # a non-blank, non-hex line: if it's another label, stop; else stop too
        # (the token should have been right here).
        return None
    return None


def _role_for_label(line: str) -> str | None:
    low = line.lower()
    for lbl, role in S3_EXACT_LABELS:
        if lbl in low:
            return role
    for role, aliases in ROLE_ALIASES.items():
        if any(a in low for a in aliases):
            return role
    return None


def parse(text: str) -> dict[str, str]:
    """Return {role: token}. Each label line is assigned to at most one role,
    and each hex line consumed at most once."""
    lines = _lines(text)
    found: dict[str, str] = {}
    used_hex: set[int] = set()
    for i, line in enumerate(lines):
        role = _role_for_label(line)
        if role is None or role in found:
            continue
        got = _extract_near(lines, i, used_hex)
        if got:
            tok, hidx = got
            found[role] = tok
            used_hex.add(hidx)
    return found


def placeholder_roles(text: str) -> list[str]:
    """Roles whose label is present but followed by an obvious placeholder, not
    a hex token — so `resolve` can say 'not filled in yet' specifically."""
    lines = _lines(text)
    out: list[str] = []
    for i, line in enumerate(lines):
        role = _role_for_label(line)
        if role is None:
            continue
        # Scan only up to the NEXT label line, so one token's placeholder is not
        # masked by the following token's hex.
        seg: list[str] = []
        for j in range(i + 1, min(i + 1 + _LOOKAHEAD, len(lines))):
            if _role_for_label(lines[j]) is not None:
                break
            seg.append(lines[j].lower())
        window = " ".join(seg)
        if not HEX_RUN.search(window) and any(h in window for h in _PLACEHOLDER_HINTS):
            out.append(role)
    return out


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
        if role in placeholder_roles(text):
            raise TokenFileError(
                f"The {ROLE_LABELS[role]} token in {path} is not filled in yet "
                "(still a <paste …> placeholder).\n"
                "  The human needs to paste the real hex token from the device/Xcode console."
            )
        expected = next((lbl for lbl, r in S3_EXACT_LABELS if r == role), ROLE_LABELS[role])
        raise TokenFileError(
            f"Could not find the {ROLE_LABELS[role]} token in {path}.\n"
            f"  Expected a line like {expected!r}\n"
            "  with a >=32-char hex token on it or the next non-blank line.\n"
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
    text = path.read_text()
    found = parse(text)
    placeholders = set(placeholder_roles(text))
    bits = [f"S3 token file: {path}  [present]"]
    for role in ROLE_ALIASES:
        tok = found.get(role)
        if tok:
            bits.append(f"  {role:<9} ({ROLE_LABELS[role]}): {tok[:6]}…{tok[-4:]} (len {len(tok)})")
        elif role in placeholders:
            bits.append(f"  {role:<9} ({ROLE_LABELS[role]}): NOT FILLED IN (placeholder)")
        else:
            bits.append(f"  {role:<9} ({ROLE_LABELS[role]}): not found")
    return "\n".join(bits)
