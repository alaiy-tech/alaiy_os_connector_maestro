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
    _seed_prompt_library()

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
    Force our singleton doctypes to actually be Singles.

    Frappe's DocType JSON single flag is the `issingle` field; a JSON that only
    carries `is_single` leaves the doctype created as a normal (multi-record)
    doctype, and Frappe blocks flipping single-ness through the ORM/migrate. A
    raw UPDATE is the supported workaround (same pattern as the Shopify
    connector). Idempotent — only touches rows that aren't already single.
    """
    for doctype in ("Maestro Connector Settings", "Maestro Credit Account"):
        if not frappe.db.exists("DocType", doctype):
            continue
        frappe.db.sql(
            "UPDATE `tabDocType` SET issingle=1 WHERE name=%s AND issingle=0",
            (doctype,),
        )
        frappe.clear_cache(doctype=doctype)
    frappe.db.commit()


DEFAULT_PROMPTS = [
    {
        "prompt_name": "White Studio BG",
        "generation_type": "Background Replace",
        "prompt_text": (
            "Replace the background with a clean seamless white studio backdrop. "
            "Keep the product, its colours, proportions and shadows exactly as they are."
        ),
    },
    {
        "prompt_name": "Outdoor Lifestyle",
        "generation_type": "Lifestyle Shot",
        "prompt_text": (
            "Place the product in a bright natural outdoor lifestyle setting with soft "
            "daylight. Keep the product unchanged and photorealistic."
        ),
    },
    {
        "prompt_name": "Flat Lay Marble",
        "generation_type": "Lifestyle Shot",
        "prompt_text": (
            "Photograph the product as a flat lay on a white marble surface, shot from "
            "above with soft even lighting. Keep the product unchanged."
        ),
    },
    {
        "prompt_name": "On-Model Lifestyle",
        "generation_type": "Lifestyle Shot",
        "prompt_text": (
            "Show the product in use in a realistic lifestyle scene with a model, "
            "natural pose and lighting. Keep the product design unchanged."
        ),
    },
]


def _seed_prompt_library():
    """Seed the 4 default Prompt Library entries (issue #7). Insert-only —
    never overwrites operator edits; is_default marks them as seeds."""
    if not frappe.db.exists("DocType", "Maestro Prompt Library"):
        return
    try:
        for seed in DEFAULT_PROMPTS:
            if frappe.db.exists("Maestro Prompt Library", seed["prompt_name"]):
                continue
            doc = frappe.new_doc("Maestro Prompt Library")
            doc.update(seed)
            doc.is_default = 1
            doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="Maestro connector: prompt seeding failed",
            message=frappe.get_traceback(),
        )


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
