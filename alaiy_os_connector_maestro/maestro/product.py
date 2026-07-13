import frappe
from frappe.utils import get_url


def _plain_description(item) -> str | None:
    """Item.description is stored as HTML; the Metadata panel wants plain text.

    Read fields with .get() — `web_long_description` isn't present on Item in
    every ERPNext version, and attribute access would raise AttributeError.
    """
    raw = item.get("description") or item.get("web_long_description") or ""
    if not raw:
        return None
    try:
        from frappe.utils import strip_html_tags
        text = strip_html_tags(raw)
    except Exception:
        text = raw
    text = (text or "").strip()
    return text or None


def _primary_image_url(item) -> str | None:
    """
    Absolute URL of the Item's primary image so Maestro can fetch it.

    Note: a private-file image (`/private/files/...`) won't be fetchable by
    Maestro without a signed token — for v1 we assume the Item image is public
    (`/files/...`), which is the ERPNext default for website/product images.
    """
    if not item.image:
        return None
    if item.image.startswith("http"):
        return item.image
    return get_url(item.image)


def _extra_fields(item) -> list[dict]:
    """
    Additional read-only Item attributes surfaced in Maestro's metadata panel.

    Each entry is ``{"label", "value"}`` and only non-empty values are kept, so
    the panel can render them generically without knowing the ERPNext schema.
    To show a new field, add it here — no Maestro/DB change is needed.
    """
    fields: list[dict] = []

    def add(label: str, value) -> None:
        if value in (None, "", 0, "0"):
            return
        fields.append({"label": label, "value": str(value).strip()})

    # Catalogue basics
    add("Stock UOM", item.get("stock_uom"))
    add("Sales UOM", item.get("sales_uom"))

    # Product type (template / variant / standalone) and lineage
    if item.get("has_variants"):
        add("Product type", "Template")
    elif item.get("variant_of"):
        add("Product type", "Variant")
        add("Variant of", item.get("variant_of"))
    else:
        add("Product type", "Standalone")

    # Variant attribute values (e.g. Color: Forest Green)
    for row in (item.get("attributes") or []):
        attr = row.get("attribute")
        val = row.get("attribute_value")
        if attr and val:
            add(attr, val)

    # Pricing (company currency; shown as-is)
    add("Standard rate", item.get("standard_rate"))

    # Physical
    weight = item.get("weight_per_unit")
    if weight:
        add("Weight", f"{weight} {item.get('weight_uom') or ''}".strip())
    add("Country of origin", item.get("country_of_origin"))

    # Status
    if item.get("disabled"):
        add("Status", "Disabled")

    return fields


def build_product_payload(item_code: str) -> dict:
    """
    Read an ERPNext Item straight from the bench DB and shape it into the
    `product` payload Maestro's create-board expects. The Frappe DB IS the
    product catalogue — no separate product store.
    """
    item = frappe.get_doc("Item", item_code)
    return {
        "item_code": item.name,
        "item_name": item.item_name or item.name,
        "description": _plain_description(item),
        "brand": item.brand or None,
        "item_group": item.item_group or None,
        "primary_image_url": _primary_image_url(item),
        "extra_fields": _extra_fields(item),
    }
