"""S2 — APNs push harness.

A standalone tool that sends all three push types (Live Activity, alert,
background/widget) to a device so that S4 can measure Live Activity behavior
without also debugging push plumbing.

Not production code. See ../DERISKING.md workstream S2.
"""

__all__ = ["config", "jwt_auth", "client", "payloads", "history"]
