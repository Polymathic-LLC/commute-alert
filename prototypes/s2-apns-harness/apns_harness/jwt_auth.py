"""APNs provider-token (JWT) auth from a `.p8` key.

APNs accepts an ES256 JWT signed with the team's `.p8` key. Rules that bite:

- Header: {"alg": "ES256", "kid": <Key ID>}
- Claims: {"iss": <Team ID>, "iat": <issued-at, seconds>}
- APNs rejects a token older than 1 hour (`ExpiredProviderToken`, 403).
- APNs also rejects tokens refreshed *too often* — more than once per ~20 min
  can draw `TooManyProviderTokenUpdates` (429). So: cache the token and reuse it
  for a fixed lifetime well under an hour.

This module caches one signed token per (key_id, team_id) and refreshes it when
it is older than `REFRESH_AFTER`.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import jwt  # PyJWT

# Refresh comfortably before Apple's 1-hour hard limit, and comfortably after
# its ~20-minute "don't spam refreshes" limit.
REFRESH_AFTER_SECONDS = 45 * 60


@dataclass
class ProviderToken:
    value: str
    issued_at: int

    def age(self, *, now: float | None = None) -> float:
        return (now if now is not None else time.time()) - self.issued_at

    def is_stale(self, *, now: float | None = None) -> bool:
        return self.age(now=now) >= REFRESH_AFTER_SECONDS


@dataclass
class ProviderTokenSigner:
    """Signs and caches an APNs provider JWT for one key."""

    key_id: str
    team_id: str
    p8_pem: str
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _cached: ProviderToken | None = field(default=None, repr=False)
    refreshes: int = 0

    def _sign(self, issued_at: int) -> str:
        return jwt.encode(
            {"iss": self.team_id, "iat": issued_at},
            self.p8_pem,
            algorithm="ES256",
            headers={"alg": "ES256", "kid": self.key_id},
        )

    def token(self, *, force: bool = False, now: float | None = None) -> ProviderToken:
        now = time.time() if now is None else now
        with self._lock:
            if not force and self._cached is not None and not self._cached.is_stale(now=now):
                return self._cached
            issued_at = int(now)
            self._cached = ProviderToken(value=self._sign(issued_at), issued_at=issued_at)
            self.refreshes += 1
            return self._cached

    def authorization_header(self, **kw) -> str:
        return f"bearer {self.token(**kw).value}"


def decode_unverified(token: str) -> dict:
    """Inspect a token we just made (header + claims), no signature check."""
    header = jwt.get_unverified_header(token)
    claims = jwt.decode(token, options={"verify_signature": False})
    return {"header": header, "claims": claims}
