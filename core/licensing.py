"""FailFixer – Offline license-key system.

This is a simple HMAC-SHA256-based license scheme designed as a **basic
piracy deterrent** — NOT enterprise-grade DRM.  A determined attacker with
access to the source can bypass it.  The goal is to make casual sharing
inconvenient while keeping the experience smooth for paying customers.

Key format:  FFX1-<payload_b64>-<sig_b64>
  - payload is JSON: {licensee, machine, issued, expires, tier}
  - sig is HMAC-SHA256(payload_bytes, secret) truncated to 16 bytes

Machine fingerprint is a best-effort stable hash of hostname + OS + platform
node / volume serial so a key cannot trivially be copied to another PC.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import subprocess
import time
from typing import Any, Optional, Tuple

# ---------------------------------------------------------------------------
# Default secret – used ONLY during development / testing.
# In production the seller tool reads FAILFIXER_LICENSE_SECRET from the
# environment and the app embeds its own copy (or also reads the env var).
# Changing this constant invalidates every key ever issued with it.
# ---------------------------------------------------------------------------
_DEFAULT_SECRET = "FFX-dev-secret-CHANGE-ME-before-release"

# Signature length (bytes) – 16 bytes = 128 bits, plenty for deterrence.
_SIG_BYTES = 16


# ======================================================================
# Machine fingerprint
# ======================================================================

def machine_fingerprint() -> str:
    """Return a stable hex fingerprint for the current machine.

    Combines hostname, OS identifier, and a volume/node identifier.
    Falls back gracefully when any piece is unavailable.
    """
    parts: list[str] = [
        platform.node(),           # hostname
        platform.system(),         # e.g. 'Windows'
        platform.machine(),        # e.g. 'AMD64'
    ]

    # Try to get Windows volume serial (most stable per-install id).
    vol_serial = _windows_volume_serial()
    if vol_serial:
        parts.append(vol_serial)
    else:
        # Fallback: uuid.getnode() returns MAC address as int – not perfect
        # but good enough cross-platform.
        import uuid
        parts.append(str(uuid.getnode()))

    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _windows_volume_serial() -> Optional[str]:
    """Return the C: volume serial number on Windows, or None."""
    if platform.system() != "Windows":
        return None
    try:
        out = subprocess.check_output(
            ["cmd", "/c", "vol", "C:"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        for line in out.splitlines():
            if "Serial" in line or "serial" in line:
                # Line looks like: " Volume Serial Number is XXXX-XXXX"
                return line.strip().split()[-1]
    except Exception:
        pass
    return None


# ======================================================================
# Key generation (seller-side)
# ======================================================================

def generate_license(
    licensee: str,
    machine_fp: str,
    expires_at: Optional[float] = None,
    tier: str = "standard",
    secret: Optional[str] = None,
) -> str:
    """Generate a license key string.

    Parameters
    ----------
    licensee : str
        Customer name / email.
    machine_fp : str
        Target machine fingerprint (from ``machine_fingerprint()``).
    expires_at : float | None
        Unix timestamp when the key expires.  ``None`` = never.
    tier : str
        License tier label (e.g. "standard", "pro").
    secret : str | None
        HMAC secret.  Falls back to env ``FAILFIXER_LICENSE_SECRET``
        then the built-in dev default.

    Returns
    -------
    str
        License key in format ``FFX1-<payload>-<sig>``.
    """
    secret = _resolve_secret(secret)

    claims: dict[str, Any] = {
        "licensee": licensee,
        "machine": machine_fp,
        "issued": time.time(),
        "tier": tier,
    }
    if expires_at is not None:
        claims["expires"] = expires_at

    payload_bytes = json.dumps(claims, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)

    sig = _sign(payload_bytes, secret)
    sig_b64 = _b64url_encode(sig)

    return f"FFX1-{payload_b64}-{sig_b64}"


# ======================================================================
# Key verification (app-side)
# ======================================================================

def verify_license(
    key: str,
    expected_machine_fp: str,
    secret: Optional[str] = None,
) -> Tuple[bool, str, dict]:
    """Verify a license key offline.

    Returns
    -------
    (ok, reason, claims)
        ok : bool – True if valid.
        reason : str – Human-readable explanation.
        claims : dict – Decoded claims (empty on failure).
    """
    secret = _resolve_secret(secret)

    # --- Parse key format ---
    parts = key.strip().split("-", 2)
    if len(parts) != 3 or parts[0] != "FFX1":
        return False, "Invalid key format.", {}

    _, payload_b64, sig_b64 = parts

    # --- Decode ---
    try:
        payload_bytes = _b64url_decode(payload_b64)
        sig_bytes = _b64url_decode(sig_b64)
    except Exception:
        return False, "Key contains invalid encoding.", {}

    # --- Verify signature ---
    expected_sig = _sign(payload_bytes, secret)
    if not hmac.compare_digest(sig_bytes, expected_sig):
        return False, "Invalid key (signature mismatch).", {}

    # --- Decode claims ---
    try:
        claims: dict = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return False, "Corrupt key payload.", {}

    # --- Machine check ---
    claim_machine = claims.get("machine")
    # Special test/beta mode: "*" works on any machine.
    # Keep this for controlled tester distribution only.
    if claim_machine not in (expected_machine_fp, "*"):
        return False, "Key is not activated for this machine.", {}

    # --- Expiry check ---
    expires = claims.get("expires")
    if expires is not None:
        try:
            if time.time() > float(expires):
                return False, "License key has expired.", claims
        except (TypeError, ValueError):
            return False, "Invalid expiry in key.", {}

    return True, "License valid.", claims


# ======================================================================
# Internal helpers
# ======================================================================

def _resolve_secret(secret: Optional[str]) -> str:
    """Return the secret to use for HMAC, checking env then fallback."""
    if secret:
        return secret
    return os.environ.get("FAILFIXER_LICENSE_SECRET", _DEFAULT_SECRET)


def _sign(payload: bytes, secret: str) -> bytes:
    """HMAC-SHA256, truncated to ``_SIG_BYTES``."""
    mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256)
    return mac.digest()[:_SIG_BYTES]


def _b64url_encode(data: bytes) -> str:
    """URL-safe base64 encode, strip padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """URL-safe base64 decode, re-add padding."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)
