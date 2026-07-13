import frappe
from frappe.model.document import Document


class MaestroGenerationJob(Document):
    pass


@frappe.whitelist()
def set_result_status(job_id: str, result_row: str, status: str) -> dict:
    """
    Accept/Discard a single result row from the review grid.
    `result_row` is the child row name; `status` is Accepted or Discarded.
    """
    if status not in ("Accepted", "Discarded", "Pending Review"):
        frappe.throw("Invalid review status")

    job = frappe.get_doc("Maestro Generation Job", job_id)
    row = next((r for r in job.results if r.name == result_row), None)
    if not row:
        frappe.throw("Result row not found")
    if not row.generated_image_url:
        frappe.throw("This result has no generated image to review")

    row.status = status
    job.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "status": status}


@frappe.whitelist()
def save_accepted(job_id: str) -> dict:
    """
    Persist every Accepted result into Alaiy OS — attach the generated image to
    the Item (or create a variant when the row asks for one). Reuses the same
    image_save machinery as the single-product save-back, so behaviour is
    identical to the Metadata-panel flow.
    """
    from alaiy_os_connector_maestro.maestro.image_save import (
        attach_image_to_item,
        create_item_variant_with_image,
    )

    job = frappe.get_doc("Maestro Generation Job", job_id)
    saved, failed = 0, 0

    for row in job.results:
        if row.status != "Accepted" or not row.generated_image_url:
            continue
        try:
            if row.save_mode == "Create Variant" and (row.variant_name or "").strip():
                create_item_variant_with_image(
                    row.item_code,
                    row.generated_image_url,
                    row.variant_name.strip(),
                    (row.variant_attribute or "Color").strip(),
                )
            else:
                attach_image_to_item(row.item_code, row.generated_image_url)
            row.status = "Saved"
            saved += 1
        except Exception:
            failed += 1
            row.error_message = frappe.get_traceback()[-500:]
            frappe.log_error(
                title=f"Maestro: save_accepted failed for {row.item_code}",
                message=frappe.get_traceback(),
            )

    job.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "saved": saved, "failed": failed}
