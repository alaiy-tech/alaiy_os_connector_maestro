"""
Single source of truth for this connector's registration metadata.
Consumed by setup/install.py → upserted into alaiy_os's OS Connector Registry.

Maestro is an on-demand *integration* (open a product in the Maestro studio and
save generated images back), not a sync channel — so it has no
sync_categories/sync_items methods, unlike the Shopify channel connector.
"""

connector_meta = {
    "connector_id": "maestro",
    "connector_name": "Maestro",
    "connector_app": "alaiy_os_connector_maestro",
    "connector_type": "integration",
    "description": "Maestro AI image studio — generate catalogue imagery for a product and save it back",
    "icon": "image",
    "icon_url": "",
    "settings_doctype": "Maestro Connector Settings",
    "test_method": "alaiy_os_connector_maestro.api.test_connection.test_connection",
    "is_enabled": 0,
    "connection_status": "untested",
}
