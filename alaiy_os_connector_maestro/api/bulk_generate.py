"""
Bulk generation (issues #4/#8): submit N selected Items to Maestro in one job,
receive per-product callbacks as images complete, and let the operator review
Accept/Discard in the Maestro Generation Job form before saving.

Flow:
  Item list bulk action → `bulk_generate` (session-authenticated)
    → creates a Maestro Generation Job (+ one child row per item)
    → POST Maestro /api/alaiy-os/bulk-generate (202)
  Maestro generates with concurrency, then per product:
    → POST back to `bulk_result` (HMAC-validated, allow_guest)
    → child row gets generated_image_url + "Pending Review"
  Final callback {status: "all_done"} → job status Done/Failed.
"""

import json
import uuid

import frappe
from frappe import _
from frappe.utils import get_url

from alaiy_os_connector_maestro.maestro.auth import validate_callback
from alaiy_os_connector_maestro.maestro.client import MaestroClient
from alaiy_os_connector_maestro.maestro.product import build_product_payload

BULK_CALLBACK_PATH = "/api/method/alaiy_os_connector_maestro.api.bulk_generate.bulk_result"

# UI label ↔ Maestro API generation_type
GENERATION_TYPES = {
    "Background Replace": "background_replace",
    "Colour Variant": "colour_variant",
    "Lifestyle Shot": "lifestyle_shot",
}


@frappe.whitelist()
def bulk_generate(item_codes, prompt: str, generation_type: str, prompt_library: str | None = None) -> dict:
    """
    Called by the Item list "Generate Images (Maestro)" dialog.
    `item_codes` is a JSON list of Item names; items without an image are
    skipped (reported back to the dialog, not an error).
    """
    settings = frappe.get_single("Maestro Connector Settings")
    if not settings.enabled:
        frappe.throw(_("The Maestro connector is disabled. Enable it in Maestro Connector Settings."))

    if isinstance(item_codes, str):
        item_codes = json.loads(item_codes)
    if not item_codes:
        frappe.throw(_("Select at least one item."))

    prompt = (prompt or "").strip()
    if not prompt:
        frappe.throw(_("A prompt is required."))
    if generation_type not in GENERATION_TYPES:
        frappe.throw(_("Invalid generation type."))

    # Build the products payload; skip items with no image.
    products, skipped = [], []
    for code in item_codes:
        if not frappe.db.exists("Item", code):
            skipped.append({"item_code": code, "reason": "not found"})
            continue
        payload = build_product_payload(code)
        if not payload.get("primary_image_url"):
            skipped.append({"item_code": code, "reason": "no image"})
            continue
        products.append(
            {
                "item_code": payload["item_code"],
                "item_name": payload["item_name"],
                "image_url": payload["primary_image_url"],
            }
        )

    if not products:
        frappe.throw(_("None of the selected items have a product image."))

    job_id = uuid.uuid4().hex

    # Job record first — so the callback always has a row to land on, even if
    # Maestro answers before this request finishes.
    job = frappe.new_doc("Maestro Generation Job")
    job.job_id = job_id
    job.status = "Queued"
    job.generation_type = generation_type
    job.prompt_used = prompt
    job.product_count = len(products)
    job.submitted_by = frappe.session.user
    job.submitted_at = frappe.utils.now_datetime()
    for p in products:
        job.append(
            "results",
            {
                "item_code": p["item_code"],
                "item_name": p["item_name"],
                "source_image_url": p["image_url"],
                "status": "Queued",
            },
        )
    job.insert(ignore_permissions=True)
    frappe.db.commit()

    if prompt_library:
        from alaiy_os_connector_maestro.alaiy_os_connector_maestro.doctype.maestro_prompt_library.maestro_prompt_library import (
            bump_usage,
        )
        bump_usage(prompt_library)

    try:
        resp = MaestroClient(settings).bulk_generate(
            job_id=job_id,
            prompt=prompt,
            generation_type=GENERATION_TYPES[generation_type],
            products=[{"item_code": p["item_code"], "image_url": p["image_url"]} for p in products],
            callback_url=get_url(BULK_CALLBACK_PATH),
        )
    except Exception as e:
        job.reload()
        job.status = "Failed"
        job.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.log_error(title="Maestro: bulk-generate submit failed", message=frappe.get_traceback())
        frappe.throw(_("Could not submit the job to Maestro: {0}").format(str(e)[:200]))

    if not resp.get("success", True):
        job.reload()
        job.status = "Failed"
        job.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw(_("Maestro rejected the job: {0}").format(resp.get("error", "unknown")[:200]))

    job.reload()
    job.status = "Processing"
    job.save(ignore_permissions=True)
    frappe.db.commit()

    return {"job_id": job_id, "job_name": job.name, "submitted": len(products), "skipped": skipped}


@frappe.whitelist(allow_guest=True)
def bulk_result():
    """
    Maestro → Alaiy OS per-product callback (HMAC-validated).

    Body: {callback_token, job_id, item_code?, status, output_url?, error?}
      status "done"     → row gets the image, moves to Pending Review
      status "failed"   → row gets the error, moves to Failed
      status "all_done" → job closes (Done, or Failed if nothing succeeded)
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

    job_id = payload.get("job_id")
    if not job_id or not frappe.db.exists("Maestro Generation Job", job_id):
        frappe.response.status_code = 404
        return {"success": False, "error": "job not found"}

    try:
        job = frappe.get_doc("Maestro Generation Job", job_id)
        status = payload.get("status")

        if status == "all_done":
            job.status = "Done" if (job.completed_count or 0) > 0 else "Failed"
            job.completed_at = frappe.utils.now_datetime()
        elif status in ("done", "failed"):
            item_code = payload.get("item_code")
            row = next(
                (r for r in job.results if r.item_code == item_code and r.status == "Queued"),
                None,
            ) or next((r for r in job.results if r.item_code == item_code), None)
            if not row:
                frappe.response.status_code = 404
                return {"success": False, "error": f"no result row for {item_code}"}

            if status == "done":
                row.generated_image_url = payload.get("output_url")
                row.status = "Pending Review"
                job.completed_count = (job.completed_count or 0) + 1
            else:
                row.error_message = (payload.get("error") or "generation failed")[:500]
                row.status = "Failed"
                job.failed_count = (job.failed_count or 0) + 1
        else:
            frappe.response.status_code = 400
            return {"success": False, "error": "invalid status"}

        job.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Maestro: bulk_result failed", message=frappe.get_traceback())
        frappe.response.status_code = 500
        return {"success": False, "error": str(e)[:200]}
