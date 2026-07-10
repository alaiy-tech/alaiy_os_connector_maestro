# Maestro ↔ Alaiy OS Connector — Product Perspective Spec

> Version: 0.2 — Updated with real codebase analysis  
> Author: Product  
> Status: For review  
> Last updated: 2026-07-10

---

## 1. What This Is

A native connector between Maestro (Alaiy's AI creative platform) and Alaiy OS (the ecommerce operating system on Frappe/ERPNext). An operator clicks a product in Alaiy OS, Maestro opens in a new tab with that product pre-loaded on a canvas, they generate images using Maestro's existing AI tools, and save results back to the product in Alaiy OS — without copying files or switching tools.

Benchmark: **PhotoRoom**. Beat its experience for ecommerce catalogue image production.

---

## 2. Codebase Reality (Maestro)

What we found in the Maestro repo that directly shapes this spec:

| What | Detail |
|---|---|
| Stack | Next.js 16, React 19, TypeScript, Supabase (PostgreSQL + Auth + Storage) |
| AI | Google Gemini (Vertex AI) — not Stability or Replicate |
| Image storage | Supabase storage, `moodboard-images` bucket |
| Auth | Supabase JWT via `getCurrentUser()` on every route |
| Canvas data model | `boards` table + `canvas_elements` table |
| Studio URL | `/studio?mId=<board_id>` — this is the main canvas page |
| Collaboration | `board_collaborators` table + token-based sharing links |
| Board domain | `ProductDomain = "fashion" \| "home_decor"` — we add `"ecommerce"` |
| Background removal | Two paths: `POST /api/remove-bg` → Modal.run endpoint, AND bubble-action `bgremoval` → Gemini |
| Color variants | `POST /api/color-variants` — parallel Gemini calls per colour |
| Element actions | `POST /api/bubble-action` — `flatshoot`, `flatsketch`, `techsketch`, `bgremoval`, `upscale4k`, `fabricswatch` |
| Inpaint | `POST /api/inpaint` — Gemini with lasso/rect mask |
| Image type | `CanvasImage` — `src`, `originalWidth`, `originalHeight`, `sourceType`, `hasBgRemoved`, `bubbleView` |

---

## 3. The Problem

Ecommerce brand operators need lifestyle imagery, clean product shots, and colour variants for their catalogue. Today:

1. Find the product image (download from ERP or Drive)
2. Open PhotoRoom or a separate tool
3. Generate
4. Download
5. Re-upload to Alaiy OS / Shopify

That's a 5-step context switch per product. For a 200-SKU catalogue, operators give up halfway and ship with inconsistent imagery.

Alaiy OS has all the product data. Maestro has the generation capability. This connector collapses those steps into one.

---

## 4. Who Uses This

**Primary:** Catalogue Manager / Creative Ops at a D2C brand. Responsible for making sure products have good images before going live.

**Secondary:** Founder doing their own catalogue work.

**Not the target:** Fashion designers building a collection — that's Maestro's core use case. This connector is for ecommerce operators producing images at scale for an existing product catalogue.

---

## 5. Core User Journeys

### 5.1 Single Product — Quick Edit

1. Operator opens an Item in Alaiy OS. Clicks **"Open in Maestro"** button.
2. Alaiy OS connector:
   - Calls Maestro's new `POST /api/alaiy-os/create-board` endpoint (service API key)
   - Maestro creates a board (`domain: "ecommerce"`) under a dedicated service account
   - Adds the product's primary image as a `CanvasImage` canvas element on that board
   - Adds product title and description as a `CanvasText` element
   - Adds the operator's email as a board collaborator (editor role)
   - Returns the board ID
3. Connector constructs the URL: `https://maestro.alaiy.com/studio?mId=<board_id>&alaiyos=1`
4. New tab opens. Operator is already logged into Maestro (same credentials as Alaiy OS). They land directly on the board.
5. Operator uses existing Maestro tools:
   - **Background removal** — `/api/remove-bg` (Modal.run) or bubble-action `bgremoval`
   - **Colour variants** — `/api/color-variants`
   - **Lifestyle / styled shots** — `/api/generate-image` with a prompt
   - **Inpaint** — `/api/inpaint` for targeted edits
6. When happy with a result, operator clicks **"Save to Alaiy OS"** (shown when `?alaiyos=1` is in URL).
7. A panel slides in with two options:
   - **Add image to product** — saves as additional image on the Item
   - **Create new variant** — operator types variant name (e.g. "Navy Blue") and attribute (e.g. Color)
8. Maestro calls back to Alaiy OS. Image downloads and attaches. Confirmation toast appears.

### 5.2 Bulk Generation

1. Operator selects multiple Items in Alaiy OS list view → **"Generate Images (Bulk)"**
2. Bulk panel opens (Frappe dialog):
   - Prompt selector (from Prompt Library or free text)
   - Generation type: Background Replace / Colour Variant / Lifestyle Shot
3. Click **Generate** → job submitted to Maestro's `POST /api/alaiy-os/bulk-generate`
4. Job runs async. Progress tracked in **Maestro Generation Job** DocType.
5. Operator reviews results in the Job Log — accept or discard each image.
6. Accepted images attach to their respective Items.

---

## 6. What Changes in Maestro

Minimal surgery to existing code. Three additions:

### 6.1 New domain value: `"ecommerce"`

In `types/board.ts`, add `"ecommerce"` to `ProductDomain`. This tells the generation pipeline to use product-focused prompt language instead of garment/fashion language.

```ts
export type ProductDomain = "fashion" | "home_decor" | "ecommerce";
```

### 6.2 New API routes: `/api/alaiy-os/*`

Three new routes, all authenticated via a shared service API key (not Supabase JWT — these are server-to-server calls from Alaiy OS).

**`POST /api/alaiy-os/create-board`**

Creates a board, seeds it with the product image and metadata, adds the operator as collaborator.

Request:
```json
{
  "api_key": "<ALAIY_OS_CONNECTOR_API_KEY>",
  "operator_email": "ops@brand.com",
  "product": {
    "item_code": "TSHIRT-001",
    "item_name": "Spiral Tie-Dye Hoodie",
    "description": "Heavyweight cotton hoodie",
    "primary_image_url": "https://alaiy-os.example.com/files/tshirt-001.jpg",
    "additional_images": [],
    "variants": [
      { "variant_id": "TSHIRT-001-BLU", "name": "Blue", "image_url": "..." }
    ]
  },
  "callback_url": "https://alaiy-os.example.com/api/method/alaiy_maestro.receive_image",
  "callback_token": "<hmac_token>"
}
```

Response:
```json
{
  "board_id": "uuid",
  "studio_url": "https://maestro.alaiy.com/studio?mId=<uuid>&alaiyos=1"
}
```

What it does server-side (using Supabase admin client, not user JWT):
1. Creates board: `{ title: item_name, domain: "ecommerce", created_by: SERVICE_USER_ID, is_public: false }`
2. Uploads the product image to `moodboard-images` bucket via the proxy (or direct fetch)
3. Inserts a `CanvasImage` canvas element pointing to the uploaded image
4. Inserts a `CanvasText` element with product title + description (top-left, small font)
5. Adds `operator_email` as a `board_collaborators` row with `role: "editor"`
6. Stores `callback_url` + `callback_token` + `item_code` in a new `alaiy_os_context` JSONB column on the board (or a separate `alaiy_os_boards` table)

**`POST /api/alaiy-os/save-image`**

Called by the Maestro frontend when operator clicks "Save to Alaiy OS". Proxies the save-back to Alaiy OS.

Request (from Maestro frontend via server action):
```json
{
  "board_id": "uuid",
  "image_url": "https://maestro.alaiy.com/outputs/...",
  "save_mode": "add_to_product",
  "variant_name": null,
  "variant_attribute": null
}
```

What it does:
1. Looks up `alaiy_os_context` for this board_id
2. Calls `callback_url` (Alaiy OS) with the image data + `callback_token`
3. Returns success/error to the frontend

**`POST /api/alaiy-os/bulk-generate`**

Accepts a list of products + a prompt, queues generation jobs.

```json
{
  "api_key": "<key>",
  "prompt": "Replace background with white studio",
  "generation_type": "background_replace",
  "callback_url": "https://alaiy-os.example.com/api/method/alaiy_maestro.bulk_result",
  "callback_token": "<hmac_token>",
  "products": [
    { "item_code": "TSHIRT-001", "image_url": "https://..." }
  ]
}
```

Uses the existing `/api/remove-bg` (Modal.run) for background replacement and `/api/generate-image` for lifestyle/variant generation. Calls back to Alaiy OS as each image completes.

### 6.3 Canvas UI — "Save to Alaiy OS" button

When `?alaiyos=1` is present in the studio URL, the `StudioPageClient.tsx` renders an additional button in the toolbar: **"Save to Alaiy OS"**.

On click:
- Opens a slide-over panel
- Shows: "Add to product" / "Create variant" toggle
- If "Create variant": text field for variant name, select for attribute (Color / Size / etc.)
- Submit → calls `POST /api/alaiy-os/save-image` server action with the currently selected canvas image's URL

The rest of the canvas (all existing tools: bubble actions, generate, inpaint, color variants) runs completely unchanged.

---

## 7. Alaiy OS — Custom DocTypes (Connector App)

`alaiy-maestro-connector` is a Frappe app. When installed, it creates these DocTypes:

### Maestro Connector Settings (Singleton)

| Field | Type | Notes |
|---|---|---|
| maestro_base_url | Data | e.g. `https://maestro.alaiy.com` |
| api_key | Password | `ALAIY_OS_CONNECTOR_API_KEY` value |
| enabled | Check | Master on/off |
| default_generation_type | Select | Background Replace / Colour Variant / Lifestyle Shot |

### Maestro Prompt Library

| Field | Type | Notes |
|---|---|---|
| prompt_name | Data | Human name, e.g. "White Studio BG" |
| prompt_text | Small Text | Sent verbatim to Maestro |
| generation_type | Select | Background Replace / Lifestyle / Variant / Custom |
| is_default | Check | Pre-fills the bulk panel |
| usage_count | Int | Read-only, auto-incremented |

### Maestro Generation Job

| Field | Type | Notes |
|---|---|---|
| job_id | Data | UUID from Maestro |
| status | Select | Queued / Processing / Done / Failed |
| prompt_used | Small Text | |
| generation_type | Select | |
| product_count | Int | |
| completed_count | Int | |
| failed_count | Int | |
| submitted_by | Link → User | |
| submitted_at | Datetime | |
| completed_at | Datetime | |

### Maestro Generation Result (child of Job)

| Field | Type | Notes |
|---|---|---|
| item_code | Link → Item | |
| item_name | Data | |
| source_image_url | Data | Sent to Maestro |
| generated_image_url | Data | Returned from Maestro |
| generated_image_file | Link → File | Set after save to Frappe |
| status | Select | Pending Review / Accepted / Discarded |
| save_mode | Select | Add to Product / Create Variant |
| variant_name | Data | If creating a variant |
| variant_attribute | Data | e.g. "Color" |
| error_message | Small Text | If generation failed |
| reviewed_by | Link → User | |
| reviewed_at | Datetime | |

### Maestro Item Session (audit log)

| Field | Type | Notes |
|---|---|---|
| item_code | Link → Item | |
| board_id | Data | Maestro board UUID |
| opened_by | Link → User | |
| opened_at | Datetime | |
| images_saved | Int | Count of saves in this session |
| variants_created | Int | Count of variants created |

---

## 8. Alaiy OS — Frappe Whitelisted Endpoints

Two new whitelisted methods registered by the connector app:

**`alaiy_maestro.receive_image`** — called by Maestro's `/api/alaiy-os/save-image`

1. Validates `callback_token` (HMAC-SHA256, secret = `api_key`)
2. Downloads image from `image_url` → saves as Frappe File attached to the Item
3. If `save_mode = "create_variant"`: creates the Item Variant with typed name/attribute
4. Updates the Maestro Item Session record
5. Returns `{ success: true, file_url: "...", variant_created: null | item_name }`

**`alaiy_maestro.bulk_result`** — called by Maestro as each bulk image completes

1. Validates token
2. Updates the Maestro Generation Result row: sets `generated_image_url`, `status: "Pending Review"`
3. Updates Job `completed_count` / `failed_count`
4. If all done: sets Job `status: "Done"`, sends notification to `submitted_by`

---

## 9. Alaiy OS — UI Changes

### Item Form Button

A custom button added to the Item DocType form by the connector's Client Script. Visible only when connector is enabled and item has at least one image.

**Label:** "Open in Maestro"  
**Placement:** Top-right of the form, or in the Images section — whichever is less disruptive to the existing form layout.  
**Action:** Calls a whitelisted method that triggers board creation, then opens the returned `studio_url` in a new tab.

### Item List Bulk Action

Added via a Server Script. Appears when one or more Items are selected.

**Label:** "Generate Images (Maestro)"  
**Action:** Opens the Bulk Generation dialog.

### Bulk Generation Dialog

Frappe dialog. Fields:
- Prompt: dropdown from Prompt Library + free-text fallback
- Generation type: select
- Item list: read-only grid showing selected items with thumbnail
- "Generate" button

### Maestro Job Log

A list + detail view accessible from the Alaiy OS sidebar (Catalogue module).

Detail view shows:
- Job status + progress bar
- 2-column grid: source image thumbnail | generated image thumbnail, side by side
- Accept / Discard toggle per row
- "Save Accepted" button — triggers bulk attachment of accepted images

### Prompt Library

Simple Frappe list view for managing saved prompts.

---

## 10. Auth Model

**Single-product flow:**
- Alaiy OS connector calls Maestro with a service `api_key` (server-to-server). No user credential needed.
- Maestro adds the operator's email (`frappe.session.user`) as a board collaborator.
- Operator opens the studio URL in a new tab. They're already logged into Maestro with the same Google/email account.
- No extra login needed. The board collaborator row grants access.

**Bulk flow:**
- Same service API key. No per-user delegation needed.

**Callback security:**
- All Maestro → Alaiy OS callbacks signed with HMAC-SHA256 using the shared `api_key`.
- Alaiy OS validates before processing.

**Assumption:** Operators use the same email across Alaiy OS and Maestro. This is realistic since both are Alaiy products and the team uses Google Workspace. If an operator doesn't have a Maestro account, they'll see the standard Maestro login on first open — a one-time friction.

---

## 11. What Does NOT Change in Maestro

Everything below stays completely untouched:
- The existing canvas editor and all interaction logic
- All generation routes (`/api/generate-image`, `/api/color-variants`, `/api/bubble-action`, `/api/inpaint`, `/api/remove-bg`)
- Auth system (Supabase JWT)
- Board storage and collaboration system
- The fashion design workflow

The connector adds 3 new API routes, 1 new domain value, 1 new JSONB column on boards (or a small side table), and a "Save to Alaiy OS" button in `StudioPageClient.tsx` that renders only when `?alaiyos=1` is in the URL.

---

## 12. Out of Scope (v1)

| Not in scope | Why |
|---|---|
| SSO / single login across both systems | Email match is sufficient for v1 |
| Embed Maestro inside Alaiy OS (iframe) | New-tab avoids CORS and auth complexity |
| Auto-attach images without operator review | Quality gate — operator must approve |
| Video generation | Maestro doesn't support it yet |
| Text-to-image with no source product image | Needs a source image; v2 |
| Generate from Maestro search results (Pinterest etc.) | Ecommerce mode only uses product images |

---

## 13. Build Sequence

**Maestro side (Next.js)**

| Week | Work |
|---|---|
| 1 | Add `"ecommerce"` to `ProductDomain`. Add `alaiy_os_context` column to boards table (migration). Scaffold `/api/alaiy-os/*` routes with API key auth. |
| 2 | Implement `create-board`: board creation + image upload to Supabase storage + canvas element insert + collaborator add. Return studio URL. |
| 2 | Add "Save to Alaiy OS" button to `StudioPageClient.tsx` (conditional on `?alaiyos=1`). Implement `save-image` route + callback to Alaiy OS. |
| 3 | Implement `bulk-generate` route. Wire to existing `/api/remove-bg` and `/api/generate-image` internally. Callback on each completion. |

**Alaiy OS side (Frappe)**

| Week | Work |
|---|---|
| 1 | Create connector app scaffold. Install DocTypes. Register in OS Connector Registry. |
| 2 | Build `receive_image` whitelisted method. Build Item form button + Client Script. |
| 3 | Build Bulk Generation dialog + `bulk_result` method + Maestro Job Log UI. |
| 4 | Prompt Library UI. Default prompts. End-to-end test with real product data. |

---

## 14. Open Questions

1. **Does Maestro have a service user account** that the connector can create boards under? Or do we create boards under an "alaiy-connector@alaiy.com" Supabase user?
2. **Rate limits on generation routes** — `bubble-action` and `generate-image` both check `checkGeminiRateLimit(userId)`. Bulk jobs from Alaiy OS will hit these under the service user. Do we want a separate rate-limit bucket for connector-originated jobs?
3. **Image proxy for Alaiy OS image URLs** — `/api/alaiy-os/create-board` fetches the product image from Alaiy OS and uploads it to Maestro's Supabase storage. Alaiy OS private file URLs may require a signed token. How are private Item attachment URLs authenticated?
4. **`alaiy_os_context` storage** — simpler as a JSONB column on `boards` (one migration line) vs. a separate `alaiy_os_boards` table (cleaner schema). Recommendation: JSONB column for v1.
5. **Bulk job queue** — `/api/alaiy-os/bulk-generate` will call generation routes in sequence or parallel per product. We need to stay under Gemini rate limits. Recommendation: `pLimit(3)` (already used in the codebase in `generate-image/route.ts`).

---

## Appendix: Data Flow Diagram

```
Alaiy OS (Frappe)                           Maestro (Next.js + Supabase)
─────────────────                           ────────────────────────────

Item form
  "Open in Maestro" click
       │
       ▼ POST /api/alaiy-os/create-board (api_key)
       │   product data + operator email
       │                                    ┌─ create board (ecommerce domain)
       │                                    ├─ upload product image → Supabase storage
       │                                    ├─ insert CanvasImage element
       │                                    ├─ add operator as collaborator
       │                                    └─ store callback_url + item_code
       │
       ◄─── { board_id, studio_url } ───────
       │
       └─ open new tab → maestro.alaiy.com/studio?mId=<id>&alaiyos=1

                                            Studio loads board
                                            Operator uses existing tools:
                                              bubble-action (bgremoval, flatshoot…)
                                              generate-image
                                              color-variants
                                              inpaint
                                              remove-bg
                                            
                                            "Save to Alaiy OS" panel appears
                                            Operator picks: add image / create variant
                                            Submits
                                            │
                                            ▼ POST /api/alaiy-os/save-image
                                            looks up callback_url for this board
                                            │
                                            ▼ callback_url (Alaiy OS)
                                              alaiy_maestro.receive_image
                                              ├─ download image → Frappe File
                                              ├─ attach to Item
                                              └─ create Item Variant if needed


Bulk flow:
  Item list → select multiple → "Generate Images"
  Bulk panel → pick prompt → Generate
       │
       ▼ POST /api/alaiy-os/bulk-generate (api_key)
       │                                    ┌─ for each product:
       │                                    │   fetch image → run generation
       │                                    │   call bulk_result callback
       │                                    └─ repeat until batch done
       │
       ◄── callbacks ──────────────────────
  Maestro Job Log
  Operator reviews → Accept / Discard
  "Save Accepted" → bulk attach to Items
```
