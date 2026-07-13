import frappe
from frappe.model.document import Document


class MaestroConnectorSettings(Document):
    def validate(self):
        # Keep the OS Connector Registry's is_enabled flag in sync with this
        # singleton's toggle, so the Connectors card reflects reality.
        self._sync_registry_is_enabled()

    def _sync_registry_is_enabled(self):
        if frappe.db.exists("OS Connector Registry", "maestro"):
            frappe.db.set_value(
                "OS Connector Registry", "maestro", "is_enabled", self.enabled
            )
