"""
HMAC signing/validation for Maestro ↔ Alaiy OS callbacks.

Implements the shared contract in AUTH.md (Direction 2). Must stay byte-identical
to the Maestro (TypeScript) side in `lib/alaiy-os/hmac.ts`:
  - JSON object keys sorted recursively
  - compact separators, no spaces  -> separators=(",", ":")
  - UTF-8 literals kept             -> ensure_ascii=False
  - the signature covers the payload WITHOUT `callback_token`
"""

import hashlib
import hmac
import json

import frappe


def _secret() -> str:
    secret = frappe.get_single("Maestro Connector Settings").get_password("api_key")
    if not secret:
        raise RuntimeError("Maestro Connector api_key is not configured.")
    return secret


def canonical_json(payload: dict) -> str:
    unsigned = {k: v for k, v in payload.items() if k != "callback_token"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_payload(payload: dict, secret: str | None = None) -> str:
    secret = secret or _secret()
    body = canonical_json(payload)
    return hmac.new(secret.encode(), body.encode("utf-8"), hashlib.sha256).hexdigest()


def validate_callback(payload: dict, received_token: str) -> bool:
    """Constant-time verify the `callback_token` on an inbound Maestro callback."""
    if not received_token:
        return False
    try:
        expected = sign_payload(payload)
    except Exception:
        return False
    return hmac.compare_digest(expected, received_token)
