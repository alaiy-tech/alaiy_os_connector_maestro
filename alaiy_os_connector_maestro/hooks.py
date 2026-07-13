app_name = "alaiy_os_connector_maestro"
app_title = "Alaiy OS Connector Maestro"
app_publisher = "Alaiy OS"
app_description = "Maestro AI image studio connector for Alaiy OS"
app_email = "dev@alaiy.com"
app_license = "MIT"

# We plug into the alaiy_os connector framework + ERPNext's Item. We do NOT
# modify either app — registration happens by inserting our own row into the
# existing "OS Connector Registry" from after_migrate (same pattern as the
# Shopify connector).
required_apps = ["alaiy_os", "erpnext"]

after_migrate = [
    "alaiy_os_connector_maestro.setup.install.sync_connector_registry"
]

# Adds a "Maestro Sessions" link under the Alaiy OS sidebar's Logs group.
alaiy_os_sidebar_log_items = [
    {
        "link_type": "DocType",
        "link_to": "Maestro Item Session",
        "label": "Maestro Sessions",
        "icon": "image",
    }
]

# Injects the "Open in Maestro" button onto the ERPNext Item form.
doctype_js = {
    "Item": "public/js/item.js",
}
