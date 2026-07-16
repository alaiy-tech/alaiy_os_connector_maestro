import frappe
from frappe import _
from frappe.utils import get_url, validate_email_address

from alaiy_os_connector_maestro.maestro.client import MaestroClient
from alaiy_os_connector_maestro.maestro.product import build_product_payload

CALLBACK_PATH = "/api/method/alaiy_os_connector_maestro.api.receive_image.receive_image"


def _resolve_operator_email() -> str:
    """
    The operator email Maestro provisions a Supabase user for.

    `frappe.session.user` is the User's *login id*, which is not always an
    email — the shared ``Administrator`` account logs in as the literal string
    "Administrator", and a User may be created with a non-email login id. Maestro
    calls Supabase `createUser({ email })`, which hard-rejects a non-RFC address
    with "invalid format" (a 500 that only spares already-provisioned users like
    the dev's own account). So prefer the User record's `email` field and verify
    it's a valid address here, failing with a clear, actionable message.
    """
    session_user = frappe.session.user
    email = frappe.db.get_value("User", session_user, "email") or session_user

    if not validate_email_address(email):
        frappe.throw(
            _(
                "Your Alaiy OS account ({0}) has no valid email address, so Maestro "
                "can't create your studio session. Set a valid email on your User "
                "record (or sign in with a user account instead of Administrator)."
            ).format(session_user)
        )
    return email.strip().lower()


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

    operator_email = _resolve_operator_email()
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
