# Maestro Connector — Working Context

> Living doc. Resume from here in any chat. Last updated: 2026-07-10.
> Keep this current as decisions/build state change.

## 0. The three systems

```
Alaiy OS (Frappe/ERPNext bench)          Maestro fork (Next.js + Supabase)
─ this repo: alaiy_os_connector_maestro ─────────────────────────────────
  = the Frappe connector app                = maestro-alaiy-os
  Item DocType IS the product catalogue      canvas / AI image tools
        │                                            ▲
        │ 1. "Open in Maestro" (Item form button)    │
        │    whitelisted → create-board (api_key) ───┘  seeds canvas
        │                                            │
        └──── 2. receive_image (HMAC callback) ◄──── save-image
```

- **`alaiy_os_connector_maestro`** (THIS repo) — Frappe app, built like the reference
  `alaiy_os_connector_shopify`. Products come from the **Frappe bench itself** (ERPNext `Item`),
  no separate product DB.
- **`maestro-alaiy-os`** (`/Users/punith/Documents/Alaiy/maestro-alaiy-os`) — the Maestro fork
  (Part 1, mostly built; branch `feat/alaiy-os-connector-mode`, uncommitted).
- **Bench**: build.os.alaiy.com (see memory `ec2-build-bench`). Registry framework in the
  `alaiy_os` app (memory `connector-architecture`).

## 1. Locked decisions (2026-07-10)

| # | Decision |
|---|---|
| Ownership | I build the **whole** Frappe connector app (issue #7 reassignment — coordinate with Sarthak). |
| Scope now | **P0 single-product slice only**: Settings singleton + registry + Item "Open in Maestro" button + `receive_image` + Item Session audit. Defer bulk DocTypes (Job/Result/Prompt Library → P1 #4/#8). |
| Canvas seed | On open, create-board seeds the **product image node** onto the canvas (no on-canvas metadata card). Generated images stay on the canvas **wired to the parent image** they came from (existing bubble/wire lineage). |
| Metadata location | **Right sidebar** — replace the Presentation panel (`SplitPresentationPanel`) with a **Metadata panel** in ALAIY_OS_MODE. Shows product/item details; supports **drag-and-drop of canvas images into the metadata section** (mirror `usePresentationDrop` → new `useMetadataDrop`). *(Supersedes the earlier on-canvas metadata-card decision.)* |
| Metadata fields | Title + Item Code, Description, Brand + Item Group. (Price intentionally excluded.) Sourced from `alaiy_os_board_context`. |
| Variant metadata | Entered in the Metadata panel: drag a generated image in → give it a variant name + attribute (prefilled "<title> - <variant>"). Panel is the source of truth for save. |
| Save-back | Parent image → `add_to_product`; a variant entry in the panel → `create_variant` with its name/attribute. |
| Bug fix (DONE Phase 0) | Three spots collapsed `ecommerce`→`fashion` via `=== "home_decor" ? … : "fashion"`: `lib/boards/board-domain.ts` (generation-time; the main culprit), `lib/utils/board-utils.ts`, `hooks/useCreations.ts` (board-list deserializers). All fixed to preserve `ecommerce`. tsc clean. (The suspected `handleCreateBoard` bug was NOT real — its `createBoard` comes from `useBoards()` which unwraps to `Board`.) |

## 2. Canvas model (already exists in maestro-alaiy-os/types/moodboard.ts)

Branch UX reuses existing primitives — no new element types needed:
- `CanvasImage` — product / variant image node (`groupId`, `sourceType`).
- `CanvasText` — metadata card content.
- `CanvasWire` — `{sourceElementId → targetElementId}` = the branch connector.
- `CanvasBubble` — existing AI-action node; already wires input image → output image (this is
  how a variant gets generated, and gives us parent↔variant lineage for free).
- `CanvasGroup` — groups an image + its metadata card.

## 3. Frappe app layout to build (mirrors alaiy_os_connector_shopify)

```
alaiy_os_connector_maestro/                 # repo root (has LICENSE, spec.MD, AUTH.md, CONTEXT.md)
├── setup.py  requirements.txt  MANIFEST.in  .gitignore
└── alaiy_os_connector_maestro/
    ├── __init__.py  hooks.py  modules.txt  patches.txt
    ├── connector_meta.py           # connector_id="maestro", type="integration", test_method
    ├── setup/install.py            # sync_connector_registry + (minimal) custom fields
    ├── api/
    │   ├── test_connection.py      # test_method → GET Maestro base_url health
    │   ├── open_in_maestro.py      # whitelisted: Item → build payload → create-board → studio_url
    │   └── receive_image.py        # whitelisted(allow_guest): HMAC validate → download → attach/variant  (#11)
    ├── maestro/
    │   ├── client.py               # requests wrapper for Maestro /api/alaiy-os/* (api_key in body)
    │   ├── auth.py                 # HMAC sign/validate per AUTH.md
    │   ├── product.py              # build_product_payload(item): title/code/desc/brand/item_group + abs image URL
    │   └── image_save.py           # download → Frappe File attach; create_item_variant(...)
    ├── public/js/item.js           # doctype_js: "Open in Maestro" button (gated on enabled + has image)
    └── alaiy_os_connector_maestro/doctype/
        ├── maestro_connector_settings/   # Single: maestro_base_url, api_key(Password), enabled, default_generation_type
        └── maestro_item_session/         # audit: item_code, board_id, opened_by, opened_at, images_saved, variants_created
```

`hooks.py`: `required_apps=["alaiy_os","erpnext"]`, `after_migrate=[…install.sync_connector_registry]`,
`alaiy_os_sidebar_log_items` (Maestro Sessions log link), `doctype_js={"Item":"public/js/item.js"}`.
No scheduler/doc_events for P0.

## 4. Maestro-side changes needed (maestro-alaiy-os)

**Bug fix (do first, standalone):**
- `lib/boards/board-domain.ts` — `getBoardDomain` returns `data.domain === "home_decor" ? "home_decor" : "fashion"`, silently dropping `ecommerce`. Fix to preserve `ecommerce` (or use `normalizeDomain`). This is why an ecommerce board generates with fashion prompts.
- `hooks/useMoodboardsPage.ts` — `handleCreateBoard` navigates to `newBoard.id` but `createBoard` returns `{board,error}`; should be `newBoard.board?.id` (guard on it).

**Canvas seeding (create-board):**
- Extend `CreateBoardRequest.product` to carry description/brand/item_group.
- New module `lib/alaiy-os/canvas-seed.ts` — builds initial `canvas_state`: uploads the product
  image to `moodboard-images` and emits a single `CanvasImage` product node (no on-canvas metadata card).
- Store lineage + metadata in `alaiy_os_board_context`: item_code, item_name, description, brand,
  item_group, and the template (product) element id — so the Metadata panel and save-back can read them.
- Generated images already wire to their parent image via the existing bubble/wire path — keep that;
  it gives parent↔variant lineage on the canvas for free.

**Metadata panel (right sidebar, replaces Presentation in ALAIY_OS_MODE):**
- New `components/alaiy-os/MetadataPanel.tsx` — mirrors `SplitPresentationPanel`. Shows product/item
  details from board context. A "Variants" area accepts images **dragged from the canvas**
  (new `hooks/useMetadataDrop.ts`, mirroring `usePresentationDrop`); each dropped image gets an
  editable variant name + attribute (prefilled "<title> - <variant>").
- In `MoodboardEditor.tsx` + `EditorHeader.tsx`, gate on `ALAIY_OS_MODE`: swap the Presentation
  toggle/panel for the Metadata toggle/panel.
- Save panel reads: parent product → `add_to_product`; a panel variant entry → `create_variant`.

## 5. Integration contract (see AUTH.md — already verified byte-identical Node↔Python)

- Shared secret: Maestro env `ALAIY_OS_CONNECTOR_API_KEY` == Settings `api_key` (Password).
- Dir 1 (OS→Maestro): `api_key` in JSON body, constant-time check, 401 on mismatch.
- Dir 2 (Maestro→OS): HMAC-SHA256 `callback_token` over canonical JSON (sorted keys, `(",",":")`,
  `ensure_ascii=False`), signature excludes `callback_token`.
- `receive_image` payload: `{callback_token,item_code,image_url,save_mode,variant_name,variant_attribute}`.

## 6. Issues → this work

| Issue | State |
|---|---|
| #2 create-board (Maestro) | built; needs seeding added (§4) |
| #3 save-image + Save button (Maestro) | built |
| #7 Frappe DocTypes | **building now (P0 slice)** |
| #10 auth/HMAC | done + verified (AUTH.md) |
| #11 receive_image | **building now** |
| #12 e2e single-product | after both sides wired; needs Maestro reachable from the bench (tunnel/deploy) |
| #4/#8/#9 bulk + credits | P1, deferred |

## 7. Open items / to confirm during build
- Bench reachability: for real e2e (#12), the bench (EC2) must reach the Maestro fork
  (local → tunnel, or deploy the fork). TBD.
- Verify `OS Connector Registry` field names on the live bench before writing connector_meta
  (memory `connector-architecture` documents them; confirm at build time).
- Real `ALAIY_OS_CONNECTOR_API_KEY` value still pending from user (Maestro `.env.local` + Settings).

## 8. Phased end-to-end plan

**Phase 0 — Maestro bug fixes — ✅ DONE (2026-07-10)**
- Fixed the `ecommerce`→`fashion` collapse in 3 spots (`board-domain.ts`, `lib/utils/board-utils.ts`,
  `hooks/useCreations.ts`). `getBoardDomain` now returns ecommerce, so `getMetaPrompt` → ECOMMERCE. tsc clean.
- Remaining low-priority prompt-language spots still treat non-home_decor as "garment"
  (`bubble-prompts.ts` fabricswatch, `arrange-set/route.ts`) — fashion/ecommerce fabric-swatch wording;
  not core generation, revisit if fabricswatch is exposed in ecommerce mode.

**Phase 1 — Frappe app skeleton + registry — ✅ DONE**
- Full app scaffold (setup.py/hooks/modules/connector_meta/install), `Maestro Connector Settings`
  singleton, `test_connection` → Maestro `/api/alaiy-os/health`. Python compiles, DocType JSON valid.

**Phase 2 — Handoff — ✅ DONE**
- Frappe: `public/js/item.js` button + `api/open_in_maestro.py` + `maestro/client.py` + `maestro/product.py`.
- Maestro: `lib/alaiy-os/canvas-seed.ts` (fetch image → upload → CanvasImage node via sharp dims),
  create-board seeding, context row with product metadata + product_element_id. Migration
  `103_board_context_metadata.sql`. tsc clean.

**Phase 3 — Metadata panel (right sidebar) — ✅ DONE**
- Maestro: `components/alaiy-os/MetadataPanel.tsx` + `hooks/useMetadataPanel.ts` + `hooks/useMetadataDrop.ts`
  + `app/api/alaiy-os/board-metadata/route.ts`. Presentation→Metadata swap gated on ALAIY_OS_MODE in
  MoodboardEditor + EditorHeader (Tag toggle). Drag canvas image → save candidate. Routes smoke-tested.

**Phase 4 — Save-back (receive_image) — ✅ DONE**
- Frappe: `api/receive_image.py` (HMAC-validated) + `maestro/image_save.py` (download → File → attach;
  native Item Variant with copy-Item fallback) + `Maestro Item Session` doctype + session counters.
- Save wiring lives in the Metadata panel (candidate → add_to_product / create_variant → save-image).
- **Verified: Python receive_image HMAC == Node hmac.ts byte-for-byte (incl. unicode).**

**Phase 5 — End-to-end — ✅ code complete; bench run pending**
- New Maestro routes smoke-tested (health 200/auth flag; board-metadata 400/401). Studio compiles.
- Bench install + real #12 run needs deployment + Maestro reachability — see `INSTALL.md`.

**Deferred (P1):** bulk DocTypes (Job/Result/Prompt Library), bulk-generate, AI credits (#4/#8/#9).

## 9. Open decision
- Two save surfaces currently coexist in ALAIY_OS_MODE: the FloatingActionBar Save button
  (`SaveToAlaiyOsPanel`) and the new Metadata panel. Both POST to `/api/alaiy-os/save-image`.
  Decide whether to retire the floating-bar Save in favour of the panel (leaning yes).
```
