// Adds an "Open in Maestro" button to the Item form. Injected via hooks.py's
// doctype_js — it only ADDS a button, it does not modify the core Item form.
frappe.ui.form.on("Item", {
  refresh(frm) {
    if (frm.is_new()) return;

    frappe.db
      .get_single_value("Maestro Connector Settings", "enabled")
      .then((enabled) => {
        if (!enabled) return;
        // Needs a product image to hand off to the canvas.
        if (!frm.doc.image) return;

        frm.add_custom_button(__("Open in Maestro"), () => {
          frappe.call({
            method:
              "alaiy_os_connector_maestro.api.open_in_maestro.open_in_maestro",
            args: { item_code: frm.doc.name },
            freeze: true,
            freeze_message: __("Opening Maestro…"),
            callback(r) {
              const res = r.message || {};
              if (res.studio_url) {
                window.open(res.studio_url, "_blank", "noopener");
              } else {
                frappe.msgprint(__("Could not open Maestro."));
              }
            },
          });
        });
      });
  },
});
