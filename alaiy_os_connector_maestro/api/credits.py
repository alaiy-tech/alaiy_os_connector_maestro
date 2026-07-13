"""
AI credit balance endpoints called by Maestro before/after generation
(issues #5/#9). Alaiy OS is the source of truth for credits; Maestro only
checks and deducts through these two HMAC-validated methods.

Both are POSTs so the payload can be signed with the same canonical-JSON
HMAC scheme as `receive_image` (see AUTH.md / maestro/auth.py).
"""

import json

import frappe

from alaiy_os_connector_maestro.maestro.auth import validate_callback


def _parse_and_validate() -> dict | None:
    """Shared guard: connector enabled, JSON body, valid HMAC. Returns the
    payload, or None after setting an error response."""
    settings = frappe.get_single("Maestro Connector Settings")
    if not settings.enabled:
        frappe.response.status_code = 403
        frappe.response["message"] = {"success": False, "error": "connector disabled"}
        return None

    try:
        payload = json.loads(frappe.request.data)
    except Exception:
        frappe.response.status_code = 400
        frappe.response["message"] = {"success": False, "error": "invalid JSON"}
        return None

    if not validate_callback(payload, payload.get("callback_token") or ""):
        frappe.response.status_code = 401
        frappe.response["message"] = {"success": False, "error": "signature validation failed"}
        return None

    return payload


def _account():
    return frappe.get_single("Maestro Credit Account")


@frappe.whitelist(allow_guest=True)
def get_credit_balance():
    """Maestro → Alaiy OS: current balance. Body: {callback_token, action}."""
    if _parse_and_validate() is None:
        return frappe.response.get("message")

    account = _account()
    total = account.total_credits or 0
    used = account.used_credits or 0
    return {
        "success": True,
        "total_credits": total,
        "remaining_credits": max(0, total - used),
    }


@frappe.whitelist(allow_guest=True)
def deduct_credits():
    """
    Maestro → Alaiy OS: deduct after a successful generation.
    Body: {callback_token, credits_used, operation, item_code, job_id}.
    """
    payload = _parse_and_validate()
    if payload is None:
        return frappe.response.get("message")

    try:
        credits_used = int(payload.get("credits_used") or 1)
    except (TypeError, ValueError):
        credits_used = 1
    if credits_used < 1:
        credits_used = 1

    try:
        account = _account()
        account.used_credits = (account.used_credits or 0) + credits_used
        account.save(ignore_permissions=True)

        _log_usage(payload, credits_used)
        frappe.db.commit()

        total = account.total_credits or 0
        return {
            "success": True,
            "remaining_credits": max(0, total - (account.used_credits or 0)),
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            title="Maestro: deduct_credits failed",
            message=frappe.get_traceback(),
        )
        frappe.response.status_code = 500
        return {"success": False, "error": str(e)[:200]}


def _log_usage(payload: dict, credits_used: int) -> None:
    """Append a Maestro Credit Log row (best-effort)."""
    try:
        operation = payload.get("operation")
        if operation not in ("Background Replace", "Colour Variant", "Lifestyle Shot"):
            operation = "Other"

        item_code = payload.get("item_code")
        if item_code and not frappe.db.exists("Item", item_code):
            item_code = None

        log = frappe.new_doc("Maestro Credit Log")
        log.timestamp = frappe.utils.now_datetime()
        log.operation = operation
        log.item_code = item_code
        log.credits_used = credits_used
        log.job_id = payload.get("job_id")
        log.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title="Maestro: failed to write credit log",
            message=frappe.get_traceback(),
        )
