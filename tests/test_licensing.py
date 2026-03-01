"""Tests for FailFixer licensing module.

Covers:
  - Machine fingerprint stability
  - Key generation and format
  - Valid key verification
  - Wrong machine rejection
  - Expired key rejection
  - Tampered key rejection
  - Bad format rejection
  - No-expiry (perpetual) key
  - Custom secret support
"""

from __future__ import annotations

import time
import pytest

from failfixer.core.licensing import (
    machine_fingerprint,
    generate_license,
    verify_license,
)


# ======================================================================
# Machine fingerprint
# ======================================================================

class TestMachineFingerprint:

    def test_returns_hex_string(self):
        fp = machine_fingerprint()
        assert isinstance(fp, str)
        assert len(fp) == 32
        # All hex chars
        int(fp, 16)

    def test_stable_across_calls(self):
        fp1 = machine_fingerprint()
        fp2 = machine_fingerprint()
        assert fp1 == fp2


# ======================================================================
# Key generation
# ======================================================================

class TestGenerateLicense:

    def test_key_format(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp)
        parts = key.split("-", 2)
        assert len(parts) == 3
        assert parts[0] == "FFX1"

    def test_key_with_expiry(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp, expires_at=time.time() + 86400)
        assert key.startswith("FFX1-")

    def test_key_without_expiry(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp, expires_at=None)
        assert key.startswith("FFX1-")

    def test_different_machines_different_keys(self):
        k1 = generate_license("user@test.com", "machine_a")
        k2 = generate_license("user@test.com", "machine_b")
        assert k1 != k2

    def test_custom_secret(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp, secret="my-custom-secret")
        assert key.startswith("FFX1-")


# ======================================================================
# Key verification — valid cases
# ======================================================================

class TestVerifyLicenseValid:

    def test_valid_key_accepts(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp)
        ok, reason, claims = verify_license(key, fp)
        assert ok is True
        assert "valid" in reason.lower()
        assert claims["licensee"] == "user@test.com"
        assert claims["machine"] == fp

    def test_valid_key_with_future_expiry(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp, expires_at=time.time() + 86400)
        ok, reason, claims = verify_license(key, fp)
        assert ok is True
        assert "expires" in claims

    def test_valid_key_no_expiry(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp, expires_at=None)
        ok, reason, claims = verify_license(key, fp)
        assert ok is True
        assert "expires" not in claims

    def test_tier_preserved(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp, tier="pro")
        ok, _, claims = verify_license(key, fp)
        assert ok is True
        assert claims["tier"] == "pro"

    def test_custom_secret_round_trip(self):
        fp = machine_fingerprint()
        secret = "test-secret-xyz"
        key = generate_license("user@test.com", fp, secret=secret)
        ok, reason, _ = verify_license(key, fp, secret=secret)
        assert ok is True


# ======================================================================
# Key verification — rejection cases
# ======================================================================

class TestVerifyLicenseReject:

    def test_wrong_machine(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp)
        ok, reason, _ = verify_license(key, "wrong_machine_fp")
        assert ok is False
        assert "not activated for this machine" in reason.lower()

    def test_expired_key(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp, expires_at=time.time() - 3600)
        ok, reason, claims = verify_license(key, fp)
        assert ok is False
        assert "expired" in reason.lower()
        # Claims should still be returned for expired keys
        assert claims.get("licensee") == "user@test.com"

    def test_bad_format_no_prefix(self):
        fp = machine_fingerprint()
        ok, reason, _ = verify_license("garbage-key", fp)
        assert ok is False
        assert "format" in reason.lower()

    def test_bad_format_wrong_prefix(self):
        fp = machine_fingerprint()
        ok, reason, _ = verify_license("FFX2-payload-sig", fp)
        assert ok is False
        assert "format" in reason.lower()

    def test_tampered_signature(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp)
        parts = key.split("-", 2)
        tampered = f"{parts[0]}-{parts[1]}-AAAAAAAAAAAAAAAA"
        ok, reason, _ = verify_license(tampered, fp)
        assert ok is False
        assert "signature" in reason.lower() or "invalid" in reason.lower()

    def test_tampered_payload(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp)
        parts = key.split("-", 2)
        # Mangle the payload
        tampered = f"{parts[0]}-AAAA{parts[1][4:]}-{parts[2]}"
        ok, reason, _ = verify_license(tampered, fp)
        assert ok is False

    def test_wrong_secret(self):
        fp = machine_fingerprint()
        key = generate_license("user@test.com", fp, secret="secret-A")
        ok, reason, _ = verify_license(key, fp, secret="secret-B")
        assert ok is False
        assert "signature" in reason.lower() or "invalid" in reason.lower()

    def test_empty_key(self):
        fp = machine_fingerprint()
        ok, reason, _ = verify_license("", fp)
        assert ok is False

    def test_whitespace_key(self):
        fp = machine_fingerprint()
        ok, reason, _ = verify_license("   ", fp)
        assert ok is False
