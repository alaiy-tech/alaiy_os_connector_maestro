import frappe


def sync_connector_registry():
    """
    Register or update the Maestro connector row in alaiy_os's OS Connector
    Registry. Called from hooks.py -> after_migrate on every bench migrate.

    This ONLY inserts/updates our own registry row and re-runs alaiy_os's own
    sidebar provisioning helpers — it never modifies the alaiy_os or erpnext
    apps themselves.
    """
    _fix_settings_as_single()

    if not frappe.db.exists("DocType", "OS Connector Registry"):
        return

    from alaiy_os_connector_maestro.connector_meta import connector_meta

    connector_id = connector_meta["connector_id"]

    if frappe.db.exists("OS Connector Registry", connector_id):
        doc = frappe.get_doc("OS Connector Registry", connector_id)
    else:
        doc = frappe.new_doc("OS Connector Registry")

    # Runtime fields are owned by test_connection at runtime — never stomp them
    # back to the seed values on a plain migrate.
    RUNTIME_FIELDS = {"connection_status", "last_tested_at"}

    if doc.is_new():
        for key, val in connector_meta.items():
            if hasattr(doc, key):
                doc.set(key, val)
        doc.insert(ignore_permissions=True)
    else:
        for key, val in connector_meta.items():
            if key not in RUNTIME_FIELDS and hasattr(doc, key):
                doc.set(key, val)
        doc.save(ignore_permissions=True)

    frappe.db.commit()
    _update_alaiy_os_sidebar()


def _fix_settings_as_single():
    """
    Force `Maestro Connector Settings` to be a Single doctype.

    Frappe's DocType JSON single flag is the `issingle` field; a JSON that only
    carries `is_single` leaves the doctype created as a normal (multi-record)
    doctype, and Frappe blocks flipping single-ness through the ORM/migrate. A
    raw UPDATE is the supported workaround (same pattern as the Shopify
    connector). Idempotent — only touches the row when it's not already single.
    """
    if not frappe.db.exists("DocType", "Maestro Connector Settings"):
        return
    frappe.db.sql(
        "UPDATE `tabDocType` SET issingle=1 "
        "WHERE name='Maestro Connector Settings' AND issingle=0"
    )
    frappe.db.commit()
    frappe.clear_cache(doctype="Maestro Connector Settings")


def _update_alaiy_os_sidebar():
    """
    Re-run alaiy_os's workspace/sidebar provisioning so this connector's Logs
    link and Connectors entry (settings button + card) appear right after it
    registers, instead of waiting for the next full bench migrate. These are
    alaiy_os's own public helpers — we call them, we don't change them.
    """
    try:
        from alaiy_os.setup.install import (
            create_or_update_workspace_sidebar,
            create_or_update_os_settings_workspace,
            create_or_update_os_settings_workspace_sidebar,
        )
        create_or_update_workspace_sidebar()
        create_or_update_os_settings_workspace()
        create_or_update_os_settings_workspace_sidebar()
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="Maestro connector: sidebar update failed",
            message=frappe.get_traceback(),
        )
