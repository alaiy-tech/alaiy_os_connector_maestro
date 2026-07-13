# Connector Auth & Signing Scheme (issue #10)

The shared contract both sides implement identically. **Maestro = the Next.js fork
(`maestro-alaiy-os`); Alaiy OS = this Frappe connector app.**

## Shared secret

One value, stored on both sides:

- **Maestro**: env `ALAIY_OS_CONNECTOR_API_KEY`
- **Alaiy OS**: `Maestro Connector Settings → api_key` (Password field)

It is used for both directions below.

## Direction 1 — Alaiy OS → Maestro (service API key)

Every call to `POST /api/alaiy-os/*` carries the key in the JSON body as `api_key`.
Maestro validates it in constant time and returns `401` on mismatch/missing.

```json
{ "api_key": "<ALAIY_OS_CONNECTOR_API_KEY>", "...": "..." }
```

## Direction 2 — Maestro → Alaiy OS (HMAC-signed callback)

When Maestro calls back to `callback_url`, it proves it is Maestro with an
HMAC-SHA256 signature sent as `callback_token` in the JSON body.

**Canonicalisation (must be byte-identical on both sides):**
- JSON object keys sorted recursively
- compact separators — no spaces
- UTF-8 literals (do **not** escape non-ASCII)
- the signature covers the payload **without** `callback_token`
- keep payloads flat string/null values (avoid floats)

**Maestro (TypeScript)** — `lib/alaiy-os/hmac.ts`:
```ts
const body = JSON.stringify(sortKeysDeep(payload)); // compact, sorted
const token = crypto.createHmac("sha256", apiKey).update(body, "utf8").digest("hex");
send({ ...payload, callback_token: token });
```

**Alaiy OS (Python)** — must match exactly:
```python
import hmac, hashlib, json

def validate_maestro_callback(payload: dict, received_token: str) -> bool:
    secret = frappe.db.get_single_value("Maestro Connector Settings", "api_key")
    unsigned = {k: v for k, v in payload.items() if k != "callback_token"}
    body = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(secret.encode(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_token)
```

> ⚠️ The two settings that make signatures match: `separators=(",", ":")` (no
> spaces — Python's default adds them) and `ensure_ascii=False` (so both keep
> UTF-8 literals). Get either wrong and every signature fails.

## save-image payload (what `receive_image` receives)

```json
{
  "item_code": "TSHIRT-001",
  "image_url": "https://<maestro-supabase>/storage/v1/object/public/moodboard-images/...",
  "save_mode": "add_to_product",
  "variant_name": null,
  "variant_attribute": null,
  "callback_token": "<hex hmac over the above, minus this field>"
}
```
