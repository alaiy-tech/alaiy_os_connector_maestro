"""
Download a Maestro-generated image and persist it into Alaiy OS: either as an
additional File on the Item, or as a new Item Variant carrying the image.

Kept separate from the whitelisted endpoint so the HTTP/HMAC layer stays thin
and this (bench-dependent) logic is unit-testable on its own.
"""

import re

import requests
import frappe
from frappe.utils.file_manager import save_file


def _download(image_url: str) -> tuple[bytes, str]:
    resp = requests.get(image_url, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type", "image/jpeg")


def _ext(content_type: str) -> str:
    if "png" in content_type:
        return "png"
    if "webp" in content_type:
        return "webp"
    return "jpg"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "variant"


def _save_file_for_item(item_code: str, image_url: str) -> str:
    """Download the image and attach it as a public File on the given Item."""
    content, content_type = _download(image_url)
    fname = f"maestro-{_slug(item_code)}-{frappe.generate_hash(length=8)}.{_ext(content_type)}"
    file_doc = save_file(fname, content, "Item", item_code, is_private=0)
    return file_doc.file_url


def attach_image_to_item(item_code: str, image_url: str) -> str:
    """
    Save the image as an additional File on the Item. If the Item has no primary
    image yet, also set it as the Item image. Returns the file URL.
    """
    file_url = _save_file_for_item(item_code, image_url)
    item = frappe.get_doc("Item", item_code)
    if not item.image:
        item.image = file_url
        item.save(ignore_permissions=True)
    return file_url


def create_item_variant_with_image(
    item_code: str,
    image_url: str,
    variant_name: str,
    variant_attribute: str,
) -> dict:
    """
    Create a new Item Variant of `item_code` for `variant_attribute = variant_name`
    and attach the image to it.

    Uses ERPNext's native variant machinery when the template is variant-ready;
    otherwise falls back to a standalone copy Item so a save never hard-fails on
    a product that wasn't pre-configured for variants. Returns
    {variant_code, file_url, mode}.
    """
    try:
        variant_code = _create_native_variant(item_code, variant_attribute, variant_name)
        mode = "item_variant"
    except Exception:
        frappe.log_error(
            title="Maestro: native variant creation failed, using copy fallback",
            message=frappe.get_traceback(),
        )
        variant_code = _create_copy_item(item_code, variant_attribute, variant_name)
        mode = "copy_item"

    file_url = attach_image_to_item(variant_code, image_url)
    return {"variant_code": variant_code, "file_url": file_url, "mode": mode}


# ── ERPNext-native variant path ────────────────────────────────────────────

def _ensure_attribute(attribute: str, value: str) -> None:
    """Ensure an Item Attribute exists and includes the given value."""
    if not frappe.db.exists("Item Attribute", attribute):
        attr = frappe.new_doc("Item Attribute")
        attr.attribute_name = attribute
        attr.append("item_attribute_values", {"attribute_value": value, "abbr": _slug(value)[:8]})
        attr.insert(ignore_permissions=True)
        return

    attr = frappe.get_doc("Item Attribute", attribute)
    if not any((v.attribute_value or "").lower() == value.lower() for v in attr.item_attribute_values):
        attr.append("item_attribute_values", {"attribute_value": value, "abbr": _slug(value)[:8]})
        attr.save(ignore_permissions=True)


def _ensure_template_ready(item_code: str, attribute: str) -> None:
    """Make the Item a variant template that carries `attribute` (if it can be)."""
    item = frappe.get_doc("Item", item_code)
    changed = False
    if not item.has_variants:
        item.has_variants = 1
        changed = True
    if not any(row.attribute == attribute for row in (item.attributes or [])):
        item.append("attributes", {"attribute": attribute})
        changed = True
    if changed:
        item.save(ignore_permissions=True)


def _create_native_variant(item_code: str, attribute: str, value: str) -> str:
    from erpnext.controllers.item_variant import create_variant, get_variant

    _ensure_attribute(attribute, value)
    _ensure_template_ready(item_code, attribute)

    args = {attribute: value}
    existing = get_variant(item_code, args)
    if existing:
        return existing

    variant = create_variant(item_code, args)
    variant.flags.ignore_permissions = True
    variant.insert()
    return variant.name


# ── Fallback: standalone copy Item ──────────────────────────────────────────

def _create_copy_item(item_code: str, attribute: str, value: str) -> str:
    """
    Non-variant fallback: clone the essentials of the template into a new Item
    named "<code>-<value>". Used when the template can't be made variant-ready
    (e.g. it already has stock transactions).
    """
    template = frappe.get_doc("Item", item_code)
    new_code = f"{item_code}-{_slug(value)}"
    if frappe.db.exists("Item", new_code):
        return new_code

    copy = frappe.new_doc("Item")
    copy.item_code = new_code
    copy.item_name = f"{template.item_name or item_code} - {value}"
    copy.item_group = template.item_group
    copy.stock_uom = template.stock_uom
    copy.brand = template.brand
    copy.description = template.description
    copy.is_stock_item = template.is_stock_item
    copy.insert(ignore_permissions=True)
    return copy.name
