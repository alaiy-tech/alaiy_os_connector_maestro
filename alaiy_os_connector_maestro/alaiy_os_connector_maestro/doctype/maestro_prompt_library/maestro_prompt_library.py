import frappe
from frappe.model.document import Document


class MaestroPromptLibrary(Document):
    pass


def bump_usage(prompt_name: str) -> None:
    """Increment usage_count on a library prompt (best-effort, never raises)."""
    try:
        if frappe.db.exists("Maestro Prompt Library", prompt_name):
            frappe.db.set_value(
                "Maestro Prompt Library",
                prompt_name,
                "usage_count",
                (frappe.db.get_value("Maestro Prompt Library", prompt_name, "usage_count") or 0) + 1,
                update_modified=False,
            )
    except Exception:
        frappe.log_error(
            title="Maestro: failed to bump prompt usage",
            message=frappe.get_traceback(),
        )
