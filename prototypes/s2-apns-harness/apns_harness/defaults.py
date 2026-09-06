"""S3-probe identifiers, authoritative as of the orchestrator handoff.

These are the throwaway App IDs S3 registered — deliberately distinct from the
production `com.polymathic.commutealert` so the probe App IDs never collide.

apns.env still wins: the loader reads APNS_TEAM_ID / APNS_BUNDLE_ID from there
if present. These constants are only the fallback, and using the fallback prints
a loud warning — the point is that a missing env var can't turn into a silent
wrong-topic failure (the exact failure mode the S2 brief calls out), not that
the env file is optional.

APNS_KEY_ID has no default on purpose: it is minted with the .p8 key and only
the human has it.
"""

TEAM_ID = "MSQSPT8P3W"
APP_BUNDLE_ID = "com.polymathic.commutealert.s3probe"
WIDGET_BUNDLE_ID = "com.polymathic.commutealert.s3probe.widget"

# For reference / assertions — derived, never sent as-is without going through config.
LIVEACTIVITY_TOPIC = f"{APP_BUNDLE_ID}.push-type.liveactivity"
PRODUCTION_BUNDLE_ID = "com.polymathic.commutealert"  # NOT for the probe

# Where S3 has the human paste the three device tokens.
S3_TOKENS_RELATIVE = "../s3-apple-setup/tokens.md"
