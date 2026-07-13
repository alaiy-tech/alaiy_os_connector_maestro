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
          // Open the tab synchronously, inside the click gesture, so popup
          // blockers (Brave/Chrome) don't kill it — create-board is async and
          // opening the tab in its callback would be treated as a non-user
          // action and silently blocked. We point the already-open tab at the
          // studio URL once the response arrives.
          const win = window.open("about:blank", "_blank");

          frappe.call({
            method:
              "alaiy_os_connector_maestro.api.open_in_maestro.open_in_maestro",
            args: { item_code: frm.doc.name },
            freeze: true,
            freeze_message: __("Opening Maestro…"),
            callback(r) {
              const res = r.message || {};
              if (res.studio_url) {
                if (win) win.location.href = res.studio_url;
                else window.open(res.studio_url, "_blank"); // popup was blocked; retry
              } else {
                if (win) win.close();
                frappe.msgprint(__("Could not open Maestro."));
              }
            },
            error() {
              if (win) win.close();
            },
          });
        });
      });
  },
});
