"""Unit tests for the APNs harness. No network, no real credentials.

Run:  .venv/bin/python -m pytest -q
"""

from __future__ import annotations

import json
import time
import types

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from apns_harness import client, config, history, jwt_auth, payloads, tokens
from apns_harness.payloads import PUSH_TYPES


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def ec_p8_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def cfg(ec_p8_pem, tmp_path) -> config.ApnsConfig:
    p8 = tmp_path / "AuthKey_KEY123.p8"
    p8.write_text(ec_p8_pem)
    return config.ApnsConfig(
        key_id="KEY123",
        team_id="TEAM123",
        bundle_id="com.example.probe",
        p8_path=p8,
        p8_pem=ec_p8_pem,
    )


# ------------------------------------------------------------------------------- jwt
def test_jwt_header_and_claims(ec_p8_pem):
    signer = jwt_auth.ProviderTokenSigner(key_id="ABC123", team_id="TEAM99", p8_pem=ec_p8_pem)
    tok = signer.token()
    info = jwt_auth.decode_unverified(tok.value)
    assert info["header"]["alg"] == "ES256"
    assert info["header"]["kid"] == "ABC123"
    assert info["claims"]["iss"] == "TEAM99"
    assert abs(info["claims"]["iat"] - int(time.time())) < 5


def test_jwt_is_cached_until_stale(ec_p8_pem):
    signer = jwt_auth.ProviderTokenSigner(key_id="K", team_id="T", p8_pem=ec_p8_pem)
    now = time.time()
    a = signer.token(now=now)
    b = signer.token(now=now + 60)  # within refresh window
    assert a.value == b.value
    assert signer.refreshes == 1
    c = signer.token(now=now + jwt_auth.REFRESH_AFTER_SECONDS + 1)
    assert c.value != a.value
    assert signer.refreshes == 2


def test_jwt_force_refresh(ec_p8_pem):
    signer = jwt_auth.ProviderTokenSigner(key_id="K", team_id="T", p8_pem=ec_p8_pem)
    a = signer.token()
    time.sleep(1)  # iat is whole seconds; ensure a different value
    b = signer.token(force=True)
    assert a.value != b.value


# ---------------------------------------------------------------------------- config
def test_env_file_parsing_and_defaults(tmp_path, monkeypatch, ec_p8_pem):
    secrets = tmp_path / ".secrets"
    secrets.mkdir()
    (secrets / "apns.env").write_text(
        "# comment\nAPNS_KEY_ID = KEYAAA \nexport APNS_TEAM_ID=\"TEAMBBB\"\n"
    )
    (secrets / "AuthKey_KEYAAA.p8").write_text(ec_p8_pem)
    monkeypatch.setattr(config, "SECRETS_DIR", secrets)
    monkeypatch.setattr(config, "ENV_FILE", secrets / "apns.env")
    for k in config.REQUIRED_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)

    cfg = config.load()
    assert cfg.key_id == "KEYAAA"
    assert cfg.team_id == "TEAMBBB"
    # bundle id absent -> S3-probe default + warning
    assert cfg.bundle_id.endswith(".s3probe")
    assert any("APNS_BUNDLE_ID" in w for w in cfg.warnings)
    assert cfg.liveactivity_topic == cfg.bundle_id + ".push-type.liveactivity"


def test_missing_key_id_is_blocking(tmp_path, monkeypatch, ec_p8_pem):
    secrets = tmp_path / ".secrets"
    secrets.mkdir()
    (secrets / "apns.env").write_text("APNS_BUNDLE_ID=com.example.x\n")
    (secrets / "AuthKey_x.p8").write_text(ec_p8_pem)
    monkeypatch.setattr(config, "SECRETS_DIR", secrets)
    monkeypatch.setattr(config, "ENV_FILE", secrets / "apns.env")
    for k in config.REQUIRED_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(config.CredentialsMissing) as exc:
        config.load()
    assert "APNS_KEY_ID" in str(exc.value)


def test_p8_must_be_pkcs8(tmp_path, monkeypatch):
    secrets = tmp_path / ".secrets"
    secrets.mkdir()
    (secrets / "apns.env").write_text("APNS_KEY_ID=K\nAPNS_TEAM_ID=T\nAPNS_BUNDLE_ID=b\n")
    (secrets / "AuthKey_K.p8").write_text("-----BEGIN EC PRIVATE KEY-----\nnope\n")
    monkeypatch.setattr(config, "SECRETS_DIR", secrets)
    monkeypatch.setattr(config, "ENV_FILE", secrets / "apns.env")
    for k in config.REQUIRED_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(config.CredentialsMissing) as exc:
        config.load()
    assert "PKCS#8" in str(exc.value) or "BEGIN PRIVATE KEY" in str(exc.value)


# -------------------------------------------------------------------------- payloads
@pytest.mark.parametrize("key", sorted(PUSH_TYPES))
def test_example_payloads_validate(key):
    pt = PUSH_TYPES[key]
    payload = payloads.example_payload(key)
    if pt.topic_kind == "liveactivity":
        payloads.inject_timestamp(payload)
    payloads.validate(payload, pt)  # must not raise


def test_liveactivity_requires_event():
    with pytest.raises(payloads.PayloadError):
        payloads.validate({"aps": {"content-state": {}}}, PUSH_TYPES["la-update"])


def test_push_to_start_requires_attributes():
    p = {"aps": {"event": "start", "content-state": {"v": 1}}}
    with pytest.raises(payloads.PayloadError):
        payloads.validate(p, PUSH_TYPES["la-start"])


def test_background_requires_content_available():
    with pytest.raises(payloads.PayloadError):
        payloads.validate({"aps": {"badge": 1}}, PUSH_TYPES["background"])


def test_payload_size_limit():
    big = {"aps": {"event": "update", "content-state": {"blob": "x" * 5000}}}
    with pytest.raises(payloads.PayloadError):
        payloads.validate(big, PUSH_TYPES["la-update"])


def test_inject_timestamp_only_when_absent():
    p = {"aps": {"event": "update", "content-state": {}}}
    assert payloads.inject_timestamp(p, now=123) is True
    assert p["aps"]["timestamp"] == 123
    assert payloads.inject_timestamp(p, now=999) is False
    assert p["aps"]["timestamp"] == 123


def test_wrong_event_for_type_warns_not_raises():
    p = {"aps": {"event": "update", "timestamp": 1, "content-state": {"v": 1}}}
    warnings = payloads.validate(p, PUSH_TYPES["la-end"])
    assert any("expected 'end'" in w for w in warnings)


# ---------------------------------------------------------------------------- client
def test_build_request_topics_per_type(cfg):
    la = client.build_request(
        cfg=cfg, push_type=PUSH_TYPES["la-update"], device_token="dead",
        payload={"aps": {}}, environment="sandbox",
    )
    assert la.headers["apns-topic"] == "com.example.probe.push-type.liveactivity"
    assert la.headers["apns-push-type"] == "liveactivity"
    assert la.url.startswith("https://api.sandbox.push.apple.com/3/device/dead")

    bg = client.build_request(
        cfg=cfg, push_type=PUSH_TYPES["background"], device_token="beef",
        payload={"aps": {}}, environment="prod",
    )
    assert bg.headers["apns-topic"] == "com.example.probe"
    assert bg.headers["apns-priority"] == "5"
    assert bg.url.startswith("https://api.push.apple.com/3/device/beef")


def test_build_request_collapse_and_expiration(cfg):
    r = client.build_request(
        cfg=cfg, push_type=PUSH_TYPES["la-update"], device_token="t",
        payload={"aps": {}}, environment="sandbox",
        collapse_id="commute-42", expiration=1700000000, priority=5,
    )
    assert r.headers["apns-collapse-id"] == "commute-42"
    assert r.headers["apns-expiration"] == "1700000000"
    assert r.headers["apns-priority"] == "5"


def test_build_request_dry_run_without_cfg_uses_probe_default():
    r = client.build_request(
        cfg=None, push_type=PUSH_TYPES["la-start"], device_token="t",
        payload={"aps": {}}, environment="sandbox",
    )
    assert r.headers["apns-topic"].endswith(".s3probe.push-type.liveactivity")


def test_parse_response_error_maps_reason():
    fake = types.SimpleNamespace(
        status_code=400,
        headers={"apns-id": "abc-123"},
        text='{"reason":"DeviceTokenNotForTopic"}',
        json=lambda: {"reason": "DeviceTokenNotForTopic"},
    )
    resp = client._parse_response(fake)  # noqa: SLF001 — testing the parser directly
    assert resp.ok is False
    assert resp.apns_id == "abc-123"
    assert resp.reason == "DeviceTokenNotForTopic"
    assert "topic" in resp.hint()


def test_parse_response_success():
    fake = types.SimpleNamespace(
        status_code=200, headers={"apns-id": "ok-1", "apns-unique-id": "u-1"},
        text="", json=lambda: {},
    )
    resp = client._parse_response(fake)  # noqa: SLF001
    assert resp.ok is True
    assert resp.reason is None


# ---------------------------------------------------------------------------- tokens
@pytest.mark.parametrize(
    "text",
    [
        "Push-to-start token: aabbccddeeff00112233445566778899aabbccddeeff0011\n"
        "Per-activity token: 1122334455667788112233445566778811223344556677881122\n"
        "Device token: ffeeddccbbaa99887766ffeeddccbbaa99887766ffeeddccbbaa\n",
        "| Live Activity push-to-start | `aabbccddeeff00112233445566778899aabbccddeeff0011` |\n"
        "| Live Activity per-activity  | `1122334455667788112233445566778811223344556677881122` |\n"
        "| plain APNs device token     | `ffeeddccbbaa99887766ffeeddccbbaa99887766ffeeddccbbaa` |\n",
        "- **push to start**\n  aabbccddeeff00112233445566778899aabbccddeeff0011\n"
        "- **activity token**\n  1122334455667788112233445566778811223344556677881122\n"
        "- **standard apns**\n  ffeeddccbbaa99887766ffeeddccbbaa99887766ffeeddccbbaa\n",
    ],
)
def test_tokens_parse_formats(text):
    found = tokens.parse(text)
    assert found["pts"].startswith("aabbcc")
    assert found["activity"].startswith("112233")
    assert found["device"].startswith("ffeedd")


# S3's actual template shape: fenced block, token on the line AFTER the label.
S3_REAL_BLOCK = """\
## Tokens

```
LIVE ACTIVITY push-to-start token:
80a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f

LIVE ACTIVITY per-activity push token:
11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff

APNs device token (alert / background):
ffeeddccbbaa00998877665544332211ffeeddccbbaa00998877665544332211
```

Captured at: <date/time>
"""


def test_tokens_parse_s3_real_format():
    found = tokens.parse(S3_REAL_BLOCK)
    assert found["pts"] == "80a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f"
    assert found["activity"] == "11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff"
    assert found["device"] == "ffeeddccbbaa00998877665544332211ffeeddccbbaa00998877665544332211"


def test_pts_label_not_claimed_by_activity_alias():
    # "LIVE ACTIVITY push-to-start token" contains the substring "activity".
    one = "LIVE ACTIVITY push-to-start token:\naa" + "b" * 40 + "\n"
    found = tokens.parse(one)
    assert set(found) == {"pts"}


def test_tokens_unfilled_placeholder_fails_loudly(tmp_path):
    f = tmp_path / "tokens.md"
    f.write_text(
        "```\n"
        "LIVE ACTIVITY push-to-start token:\n"
        "<paste — long lowercase hex, no spaces>\n\n"
        "APNs device token (alert / background):\n"
        "<paste — device token hex>\n"
        "```\n"
    )
    assert tokens.parse(f.read_text()) == {}
    with pytest.raises(tokens.TokenFileError) as exc:
        tokens.resolve("pts", path=f)
    assert "not filled in yet" in str(exc.value)


def test_tokens_blank_and_fence_between_label_and_token():
    txt = "APNs device token (alert / background):\n\n```\ndead" + "beef" * 12 + "\n```\n"
    assert tokens.parse(txt)["device"].startswith("dead")


def test_tokens_resolve_missing_file(tmp_path):
    with pytest.raises(tokens.TokenFileError):
        tokens.resolve("pts", path=tmp_path / "nope.md")


def test_tokens_resolve_role_absent(tmp_path):
    f = tmp_path / "tokens.md"
    f.write_text("push-to-start: aabbccddeeff00112233445566778899aabbccddeeff0011\n")
    assert tokens.resolve("pts", path=f).startswith("aabbcc")
    with pytest.raises(tokens.TokenFileError):
        tokens.resolve("device", path=f)


# --------------------------------------------------------------------------- history
def test_history_roundtrip(tmp_path):
    p = tmp_path / "send-history.jsonl"
    history.record({"type": "alert", "response": {"status_code": 200}}, path=p)
    history.record({"type": "la-start", "response": {"status_code": 400}}, path=p)
    rows = history.tail(10, path=p)
    assert [r["type"] for r in rows] == ["alert", "la-start"]
    assert rows[0]["logged_at_iso"]


def test_redact_token():
    assert history.redact_token("short") == "…"
    r = history.redact_token("abcdef0123456789abcdef")
    assert r.startswith("abcdef") and "len 22" in r
