# Installing the Maestro connector on the Alaiy OS bench

This app plugs into the existing `alaiy_os` connector framework. It does **not**
modify the `alaiy_os` or `erpnext` apps — it only inserts its own row into the
`OS Connector Registry` and adds an "Open in Maestro" button to the Item form
(both via standard Frappe hooks).

## 1. Install the app on the bench

```bash
# On the bench (see memory ec2-build-bench for SSH):
cd ~/frappe-bench
bench get-app alaiy_os_connector_maestro <git-url-or-local-path>
bench --site <site> install-app alaiy_os_connector_maestro
bench --site <site> migrate      # runs after_migrate -> registers the connector
bench build --app alaiy_os_connector_maestro
bench --site <site> clear-cache
```

After migrate, "Maestro" appears in **OS Settings → Connectors**, and a
"Maestro Sessions" link appears under the Alaiy OS sidebar's Logs.

## 2. Configure

Open **Maestro Connector Settings** (System Manager):

- **Maestro Base URL** — the Maestro app origin (e.g. `https://maestro.alaiy.com`
  or an ngrok URL during testing).
- **API Key** — must equal `ALAIY_OS_CONNECTOR_API_KEY` in Maestro's `.env.local`.
- **Enable Maestro** — turn on.
- Click **Test Connection** → should say "Connected to Maestro."

## 3. Reachability (both directions)

The two servers call each other, so they must be mutually reachable:

- **Bench → Maestro**: `open_in_maestro` POSTs to `<Base URL>/api/alaiy-os/create-board`.
- **Maestro → Bench**: `save-image` POSTs the signed callback to
  `<bench>/api/method/alaiy_os_connector_maestro.api.receive_image.receive_image`.

For local Maestro dev, expose it with a tunnel (e.g. `ngrok http 3000`) and set
that URL as the Base URL. The bench URL is auto-derived via `frappe.utils.get_url`.

## 4. End-to-end test (issue #12)

1. Open an Item that has a product image → **Open in Maestro** button shows.
2. Click it → a new tab opens; operator is auto-logged-in; the product image is
   on the canvas; open the right-sidebar **Product metadata** panel (tag icon) —
   title / item code / brand / item group / description show.
3. Generate an image (background remove / variant / lifestyle) — output stays on
   the canvas, wired to the parent.
4. Drag an image onto the Metadata panel → it becomes a save candidate.
   - **Add to product** → attaches as a File on the Item.
   - **Save variant** (name + attribute) → creates an Item Variant with the image.
5. Back in Alaiy OS, confirm the File / new Item Variant on the Item, and check
   the counters on the **Maestro Item Session** row.

## Known limitations (v1 / P0)

- **Private Item images**: `open_in_maestro` sends the Item image via
  `get_url`. A `/private/files/...` image won't be fetchable by Maestro without a
  signed token — assume public product images for v1.
- **Variant creation**: uses ERPNext's native `create_variant` when the template
  is variant-ready; if the item can't be made a template (e.g. it has stock
  transactions), it falls back to a standalone copy Item (`<code>-<value>`).
  Validate the desired behaviour per catalogue on the bench.
- **Bulk generation** (Job/Result/Prompt Library DocTypes, `bulk-generate`) and
  AI credits are P1 — not built.
