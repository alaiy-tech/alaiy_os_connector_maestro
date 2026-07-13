// Adds a "Generate Images (Maestro)" bulk action to the Item list view.
// Injected via hooks.py's doctype_list_js — additive only, no core changes.
frappe.listview_settings["Item"] = frappe.listview_settings["Item"] || {};

(function () {
  const settings = frappe.listview_settings["Item"];
  const previous_onload = settings.onload;

  settings.onload = function (listview) {
    if (previous_onload) previous_onload(listview);

    frappe.db
      .get_single_value("Maestro Connector Settings", "enabled")
      .then((enabled) => {
        if (!enabled) return;

        listview.page.add_actions_menu_item(
          __("Generate Images (Maestro)"),
          () => open_bulk_dialog(listview),
          true, // standard: only shown while items are checked
        );
      });
  };

  function open_bulk_dialog(listview) {
    const item_codes = listview.get_checked_items(true);
    if (!item_codes.length) {
      frappe.msgprint(__("Select at least one item."));
      return;
    }

    const d = new frappe.ui.Dialog({
      title: __("Generate Images with Maestro"),
      fields: [
        {
          fieldname: "prompt_library",
          fieldtype: "Link",
          options: "Maestro Prompt Library",
          label: __("Prompt from Library"),
          description: __("Pick a saved prompt, or write your own below."),
          onchange() {
            const name = d.get_value("prompt_library");
            if (!name) return;
            frappe.db.get_doc("Maestro Prompt Library", name).then((doc) => {
              d.set_value("prompt", doc.prompt_text || "");
              if (doc.generation_type) d.set_value("generation_type", doc.generation_type);
            });
          },
        },
        {
          fieldname: "prompt",
          fieldtype: "Small Text",
          label: __("Prompt"),
          reqd: 1,
        },
        {
          fieldname: "generation_type",
          fieldtype: "Select",
          label: __("Generation Type"),
          options: "Background Replace\nColour Variant\nLifestyle Shot",
          default: "Background Replace",
          reqd: 1,
        },
        {
          fieldname: "items_html",
          fieldtype: "HTML",
        },
      ],
      primary_action_label: __("Generate ({0} items)", [item_codes.length]),
      primary_action(values) {
        d.hide();
        frappe.call({
          method: "alaiy_os_connector_maestro.api.bulk_generate.bulk_generate",
          args: {
            item_codes: item_codes,
            prompt: values.prompt,
            generation_type: values.generation_type,
            prompt_library: values.prompt_library || null,
          },
          freeze: true,
          freeze_message: __("Submitting job to Maestro…"),
          callback(r) {
            const res = r.message || {};
            const skipped = (res.skipped || []).length;
            frappe.msgprint({
              title: __("Job Submitted"),
              indicator: "green",
              message:
                __("{0} item(s) submitted to Maestro.", [res.submitted]) +
                (skipped ? "<br>" + __("{0} skipped (no image).", [skipped]) : "") +
                `<br><a href="/app/maestro-generation-job/${encodeURIComponent(res.job_name)}">` +
                __("Open the job to review results") +
                "</a>",
            });
          },
        });
      },
    });

    // Selected-items preview (names only — cheap and clear).
    const list_html =
      `<div style="max-height:140px;overflow-y:auto;border:1px solid var(--border-color,#e5e7eb);border-radius:8px;padding:8px 12px;font-size:12px">` +
      item_codes.map((c) => `<div>${frappe.utils.escape_html(c)}</div>`).join("") +
      "</div>";
    d.get_field("items_html").$wrapper.html(
      `<label class="control-label">${__("Selected Items")}</label>${list_html}`,
    );

    d.show();
  }
})();
