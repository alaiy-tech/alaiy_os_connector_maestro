import json

import frappe

from alaiy_os_connector_maestro.maestro.auth import validate_callback
from alaiy_os_connector_maestro.maestro.image_save import (
    attach_image_to_item,
    create_item_variant_with_image,
)


@frappe.whitelist(allow_guest=True)
def receive_image():
    """
    Maestro → Alaiy OS save-back (issue #11). Called by Maestro's
    /api/alaiy-os/save-image. HMAC-validated (secret = api_key); see AUTH.md.

    Body: {callback_token, item_code, image_url, save_mode, variant_name,
    variant_attribute}. Returns {success, file_url, variant_created}.
    """
    settings = frappe.get_single("Maestro Connector Settings")
    if not settings.enabled:
        frappe.response.status_code = 403
        return {"success": False, "error": "connector disabled"}

    try:
        payload = json.loads(frappe.request.data)
    except Exception:
        frappe.response.status_code = 400
        return {"success": False, "error": "invalid JSON"}

    if not validate_callback(payload, payload.get("callback_token") or ""):
        frappe.response.status_code = 401
        return {"success": False, "error": "signature validation failed"}

    item_code = payload.get("item_code")
    image_url = payload.get("image_url")
    save_mode = payload.get("save_mode")
    if not item_code or not image_url or not save_mode:
        frappe.response.status_code = 400
        return {"success": False, "error": "item_code, image_url and save_mode are required"}
    if not frappe.db.exists("Item", item_code):
        frappe.response.status_code = 404
        return {"success": False, "error": f"Item {item_code} not found"}

    try:
        if save_mode == "create_variant":
            variant_name = (payload.get("variant_name") or "").strip()
            variant_attribute = (payload.get("variant_attribute") or "").strip()
            if not variant_name or not variant_attribute:
                frappe.response.status_code = 400
                return {
                    "success": False,
                    "error": "variant_name and variant_attribute are required for a variant",
                }
            result = create_item_variant_with_image(
                item_code, image_url, variant_name, variant_attribute
            )
            _bump_session(item_code, variants=1)
            frappe.db.commit()
            return {
                "success": True,
                "file_url": result["file_url"],
                "variant_created": result["variant_code"],
            }

        # default: add_to_product
        file_url = attach_image_to_item(item_code, image_url)
        _bump_session(item_code, images=1)
        frappe.db.commit()
        return {"success": True, "file_url": file_url, "variant_created": None}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            title="Maestro: receive_image failed",
            message=frappe.get_traceback(),
        )
        frappe.response.status_code = 500
        return {"success": False, "error": str(e)[:200]}


def _bump_session(item_code: str, images: int = 0, variants: int = 0) -> None:
    """Increment counters on the most recent open session for this item (best-effort)."""
    if not frappe.db.exists("DocType", "Maestro Item Session"):
        return
    try:
        latest = frappe.get_all(
            "Maestro Item Session",
            filters={"item_code": item_code},
            order_by="creation desc",
            limit=1,
            pluck="name",
        )
        if not latest:
            return
        doc = frappe.get_doc("Maestro Item Session", latest[0])
        doc.images_saved = (doc.images_saved or 0) + images
        doc.variants_created = (doc.variants_created or 0) + variants
        doc.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title="Maestro: failed to bump item session",
            message=frappe.get_traceback(),
        )
