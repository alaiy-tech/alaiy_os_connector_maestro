frappe.ui.form.on("Maestro Connector Settings", {
  refresh(frm) {
    frm.page.set_title(__("Maestro Settings"));

    // Mounts the shared alaiy_os connector card (status pill, enable toggle).
    if (window.alaiy_os && alaiy_os.connector_card) {
      alaiy_os.connector_card.mount(frm, "maestro");
      alaiy_os.connector_card.setup_password_reveal(frm, "api_key", "maestro");
    }

    frm.add_custom_button(
      __("Test Connection"),
      () => {
        frappe.call({
          method:
            "alaiy_os_connector_maestro.api.test_connection.test_connection",
          freeze: true,
          freeze_message: __("Pinging Maestro…"),
          callback(r) {
            const res = r.message || {};
            frappe.show_alert(
              {
                message: res.message || (res.success ? __("Connected") : __("Failed")),
                indicator: res.success ? "green" : "red",
              },
              6,
            );
          },
        });
      },
      __("Actions"),
    );
  },
});
