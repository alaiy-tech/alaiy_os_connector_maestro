// Review UI for a Maestro bulk-generation job: a before/after grid rendered
// into the `review_html` field, with Accept / Discard per result and a
// "Save Accepted" button that pushes accepted images onto their Items.
frappe.ui.form.on("Maestro Generation Job", {
  refresh(frm) {
    render_review_grid(frm);

    const accepted = (frm.doc.results || []).filter(
      (r) => r.status === "Accepted" && r.generated_image_url,
    );
    if (accepted.length) {
      frm.add_custom_button(__("Save Accepted ({0})", [accepted.length]), () => {
        frappe.call({
          method:
            "alaiy_os_connector_maestro.alaiy_os_connector_maestro.doctype.maestro_generation_job.maestro_generation_job.save_accepted",
          args: { job_id: frm.doc.name },
          freeze: true,
          freeze_message: __("Saving accepted images to Alaiy OS…"),
          callback(r) {
            const res = r.message || {};
            frappe.show_alert({
              message: __("Saved {0} image(s){1}", [
                res.saved || 0,
                res.failed ? __(", {0} failed", [res.failed]) : "",
              ]),
              indicator: res.failed ? "orange" : "green",
            });
            frm.reload_doc();
          },
        });
      }).addClass("btn-primary");
    }

    if (["Queued", "Processing"].includes(frm.doc.status)) {
      frm.add_custom_button(__("Refresh Status"), () => frm.reload_doc());
    }
  },
});

function render_review_grid(frm) {
  const wrapper = frm.get_field("review_html")?.$wrapper;
  if (!wrapper) return;

  const rows = (frm.doc.results || []).filter((r) => r.generated_image_url || r.error_message);
  if (!rows.length) {
    wrapper.html(
      `<div class="text-muted" style="padding:12px 0">${__(
        "Generated images will appear here for review as they complete.",
      )}</div>`,
    );
    return;
  }

  const badge = (status) => {
    const colors = {
      "Pending Review": "#f59e0b",
      Accepted: "#16a34a",
      Discarded: "#9ca3af",
      Saved: "#2563eb",
      Failed: "#dc2626",
      Queued: "#9ca3af",
    };
    const c = colors[status] || "#9ca3af";
    return `<span style="font-size:11px;font-weight:600;color:${c};border:1px solid ${c}33;background:${c}14;border-radius:10px;padding:2px 8px">${__(status)}</span>`;
  };

  const cards = rows
    .map((r) => {
      const img = (url, label) =>
        url
          ? `<div style="flex:1;min-width:0"><div style="font-size:10px;color:#888;margin-bottom:3px;text-transform:uppercase;letter-spacing:.04em">${label}</div>
             <img src="${frappe.utils.escape_html(url)}" style="width:100%;height:140px;object-fit:contain;border:1px solid var(--border-color,#e5e7eb);border-radius:8px;background:#fafafa"></div>`
          : "";
      const actions =
        r.status === "Pending Review" || r.status === "Accepted" || r.status === "Discarded"
          ? `<div style="display:flex;gap:6px;margin-top:8px">
               <button class="btn btn-xs btn-success mgj-review" data-row="${r.name}" data-status="Accepted" ${r.status === "Accepted" ? "disabled" : ""}>${__("Accept")}</button>
               <button class="btn btn-xs btn-default mgj-review" data-row="${r.name}" data-status="Discarded" ${r.status === "Discarded" ? "disabled" : ""}>${__("Discard")}</button>
             </div>`
          : "";
      const error = r.error_message
        ? `<div style="font-size:11px;color:#dc2626;margin-top:6px;white-space:pre-wrap">${frappe.utils.escape_html(r.error_message.slice(0, 160))}</div>`
        : "";
      return `<div style="border:1px solid var(--border-color,#e5e7eb);border-radius:10px;padding:10px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:8px">
          <a href="/app/item/${encodeURIComponent(r.item_code)}" style="font-weight:600;font-size:13px" title="${frappe.utils.escape_html(r.item_name || r.item_code)}">${frappe.utils.escape_html(r.item_name || r.item_code)}</a>
          ${badge(r.status)}
        </div>
        <div style="display:flex;gap:8px">${img(r.source_image_url, __("Before"))}${img(r.generated_image_url, __("After"))}</div>
        ${actions}${error}
      </div>`;
    })
    .join("");

  wrapper.html(
    `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;padding:6px 0">${cards}</div>`,
  );

  wrapper.find(".mgj-review").on("click", function () {
    const row = $(this).data("row");
    const status = $(this).data("status");
    frappe.call({
      method:
        "alaiy_os_connector_maestro.alaiy_os_connector_maestro.doctype.maestro_generation_job.maestro_generation_job.set_result_status",
      args: { job_id: frm.doc.name, result_row: row, status },
      callback() {
        frm.reload_doc();
      },
    });
  });
}
