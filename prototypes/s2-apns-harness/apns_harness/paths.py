"""Path resolution that survives running inside a git worktree.

S2 may execute in an isolated worktree
(`.../.claude/worktrees/<name>/prototypes/s2-apns-harness/`) while the human
drops credentials into the MAIN checkout
(`.../prototypes/s2-apns-harness/.secrets/`). Anything the human or a sibling
session writes (`.secrets/`, S3's `tokens.md`) must therefore be looked up
against the main checkout, not `__file__`'s parent.

Everything the harness itself writes and reads back on its own (`logs/`) stays
local to wherever the code runs, which is fine.
"""

from __future__ import annotations

import os
from pathlib import Path

# .../<checkout>/prototypes/s2-apns-harness  (may be inside .claude/worktrees/…)
_LOCAL_PROTOTYPE_ROOT = Path(__file__).resolve().parent.parent


def _strip_worktree(p: Path) -> Path:
    """If p is inside `.claude/worktrees/<name>/`, return the equivalent path in
    the main checkout; otherwise return p unchanged."""
    parts = p.parts
    if ".claude" in parts:
        i = parts.index(".claude")
        if parts[i + 1 : i + 3] and parts[i + 1] == "worktrees":
            repo_root = Path(*parts[:i])
            tail = Path(*parts[i + 3 :])  # drop ".claude/worktrees/<name>"
            return repo_root / tail
    return p


# Prototype root in the main checkout (where the human / sibling sessions write).
MAIN_PROTOTYPE_ROOT = _strip_worktree(_LOCAL_PROTOTYPE_ROOT)

IN_WORKTREE = MAIN_PROTOTYPE_ROOT != _LOCAL_PROTOTYPE_ROOT


def secrets_dir() -> Path:
    """Where APNs credentials live. Env override wins; otherwise the main
    checkout's `.secrets/`, falling back to the local one if that doesn't
    exist yet."""
    env = os.environ.get("APNS_SECRETS_DIR")
    if env:
        return Path(env).expanduser()
    main = MAIN_PROTOTYPE_ROOT / ".secrets"
    local = _LOCAL_PROTOTYPE_ROOT / ".secrets"
    if IN_WORKTREE and main.is_dir() and any(main.iterdir()):
        return main
    if IN_WORKTREE and not (local.is_dir() and any(local.iterdir())):
        # Nothing local either — point at the main checkout so messages name the
        # path the human is actually expected to use.
        return main
    return local


def logs_dir() -> Path:
    return _LOCAL_PROTOTYPE_ROOT / "logs"


def local_prototype_root() -> Path:
    return _LOCAL_PROTOTYPE_ROOT
