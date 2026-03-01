"""FailFixer – Lemon Squeezy license activation/validation.

Uses the public Lemon Squeezy License API (no API key needed for
activate/validate/deactivate — only the customer's license_key).

All HTTP calls use stdlib only (urllib).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEMON_API_BASE = "https://api.lemonsqueezy.com"
LEMON_TIMEOUT_SEC = 6      # short timeout for startup checks
LEMON_GRACE_DAYS = 7       # days of offline grace after last valid check


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def activate_license(
    license_key: str,
    instance_name: str,
    *,
    timeout: int = LEMON_TIMEOUT_SEC,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Activate a Lemon Squeezy license key for this instance.

    POST /v1/licenses/activate
    Form fields: license_key, instance_name

    Returns (ok, reason, data) where *data* is the parsed JSON response.
    """
    return _post(
        "/v1/licenses/activate",
        {"license_key": license_key, "instance_name": instance_name},
        timeout=timeout,
    )


def validate_license(
    license_key: str,
    instance_id: Optional[str] = None,
    *,
    timeout: int = LEMON_TIMEOUT_SEC,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate a Lemon Squeezy license key.

    POST /v1/licenses/validate
    Form fields: license_key (+ instance_id optional)

    Returns (ok, reason, data).
    """
    fields: Dict[str, str] = {"license_key": license_key}
    if instance_id:
        fields["instance_id"] = instance_id
    return _post("/v1/licenses/validate", fields, timeout=timeout)


def deactivate_license(
    license_key: str,
    instance_id: str,
    *,
    timeout: int = LEMON_TIMEOUT_SEC,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Deactivate a Lemon Squeezy license instance.

    POST /v1/licenses/deactivate
    Form fields: license_key, instance_id

    Returns (ok, reason, data).
    """
    return _post(
        "/v1/licenses/deactivate",
        {"license_key": license_key, "instance_id": instance_id},
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _post(
    path: str,
    fields: Dict[str, str],
    *,
    timeout: int = LEMON_TIMEOUT_SEC,
) -> Tuple[bool, str, Dict[str, Any]]:
    """POST form data to the Lemon Squeezy API and return (ok, reason, data).

    *ok* is True when the API returns ``"valid": true`` (or ``"activated": true``
    for the activate endpoint).

    On network errors (timeout, DNS, connection refused) the reason string
    starts with ``"network_error:"`` so callers can distinguish transient
    failures from hard rejections.
    """
    url = f"{LEMON_API_BASE}{path}"
    body = urllib.parse.urlencode(fields).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            data: Dict[str, Any] = json.loads(raw)
    except urllib.error.HTTPError as exc:
        # Lemon returns 4xx with JSON body on invalid keys etc.
        try:
            raw = exc.read()
            data = json.loads(raw)
        except Exception:
            data = {}
        reason = data.get("error", str(exc))
        return False, reason, data
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return False, f"network_error: {exc}", {}
    except Exception as exc:
        return False, f"network_error: {exc}", {}

    # Determine success from the response body
    valid = data.get("valid", False) or data.get("activated", False)
    if valid:
        reason = data.get("license_key", {}).get("status", "valid")
        return True, reason, data
    else:
        reason = data.get("error", "License not valid")
        return False, reason, data
