import requests
import frappe


class MaestroClient:
    """
    Thin wrapper over Maestro's server-to-server connector API
    (`/api/alaiy-os/*`). Every call carries the shared `api_key` in the JSON
    body (see AUTH.md, Direction 1). Reads config from the Maestro Connector
    Settings singleton.
    """

    def __init__(self, settings=None):
        settings = settings or frappe.get_single("Maestro Connector Settings")

        base = (settings.maestro_base_url or "").strip().rstrip("/")
        if not base:
            raise RuntimeError("Maestro Base URL is not configured.")
        if not base.startswith("http"):
            base = f"https://{base}"
        self.base_url = base

        self.api_key = settings.get_password("api_key") if settings.api_key else None

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _post(self, path, payload, timeout=30):
        return self.session.post(f"{self.base_url}{path}", json=payload, timeout=timeout)

    def health(self):
        """Ping Maestro and verify the api_key is accepted. Returns the response."""
        return self._post("/api/alaiy-os/health", {"api_key": self.api_key}, timeout=15)

    def create_board(self, operator_email, product, callback_url):
        """
        Ask Maestro to create an ecommerce board seeded with this product and
        return `{board_id, studio_url, auto_login, ...}`.
        """
        payload = {
            "api_key": self.api_key,
            "operator_email": operator_email,
            "product": product,
            "domain": "ecommerce",
            "callback_url": callback_url,
        }
        resp = self._post("/api/alaiy-os/create-board", payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def bulk_generate(self, job_id, prompt, generation_type, products, callback_url):
        """
        Submit a bulk-generation job. Maestro answers 202 immediately and
        reports per-product results to `callback_url` (bulk_result) as they
        complete. Returns the parsed 202 body.
        """
        payload = {
            "api_key": self.api_key,
            "job_id": job_id,
            "prompt": prompt,
            "generation_type": generation_type,
            "products": products,
            "callback_url": callback_url,
        }
        resp = self._post("/api/alaiy-os/bulk-generate", payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
