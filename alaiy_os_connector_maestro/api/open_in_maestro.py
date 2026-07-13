import frappe
from frappe import _
from frappe.utils import get_url

from alaiy_os_connector_maestro.maestro.client import MaestroClient
from alaiy_os_connector_maestro.maestro.product import build_product_payload

CALLBACK_PATH = "/api/method/alaiy_os_connector_maestro.api.receive_image.receive_image"


@frappe.whitelist()
def open_in_maestro(item_code: str) -> dict:
    """
    Called by the "Open in Maestro" button on the Item form. Builds the product
    payload from the Item, asks Maestro to create a seeded board, records the
    session, and returns the studio URL for the client to open in a new tab.
    """
    settings = frappe.get_single("Maestro Connector Settings")
    if not settings.enabled:
        frappe.throw(_("The Maestro connector is disabled. Enable it in Maestro Connector Settings."))
    if not frappe.db.exists("Item", item_code):
        frappe.throw(_("Item {0} not found.").format(item_code))

    product = build_product_payload(item_code)
    if not product.get("primary_image_url"):
        frappe.throw(_("This item has no image. Add a product image before opening it in Maestro."))

    operator_email = frappe.session.user
    callback_url = get_url(CALLBACK_PATH)

    try:
        resp = MaestroClient(settings).create_board(operator_email, product, callback_url)
    except Exception as e:
        frappe.log_error(
            title="Maestro: create-board failed",
            message=frappe.get_traceback(),
        )
        frappe.throw(_("Could not open Maestro: {0}").format(str(e)[:200]))

    board_id = resp.get("board_id")
    studio_url = resp.get("studio_url")
    if not studio_url:
        frappe.throw(_("Maestro did not return a studio URL."))

    _record_session(item_code, board_id, operator_email)

    return {"studio_url": studio_url, "board_id": board_id}


def _record_session(item_code: str, board_id: str, operator_email: str) -> None:
    """Create an audit row for this open. Skipped if the doctype isn't installed yet."""
    if not frappe.db.exists("DocType", "Maestro Item Session"):
        return
    try:
        doc = frappe.new_doc("Maestro Item Session")
        doc.item_code = item_code
        doc.board_id = board_id
        doc.opened_by = operator_email
        doc.opened_at = frappe.utils.now_datetime()
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="Maestro: failed to record item session",
            message=frappe.get_traceback(),
        )
