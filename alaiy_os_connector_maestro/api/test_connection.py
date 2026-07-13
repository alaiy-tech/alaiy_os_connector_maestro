import requests
import frappe

from alaiy_os_connector_maestro.maestro.client import MaestroClient


@frappe.whitelist()
def test_connection():
    """
    Connector `test_method` (see connector_meta). Pings Maestro's health
    endpoint with the configured api_key. Returns {success, message}.
    """
    settings = frappe.get_single("Maestro Connector Settings")

    if not (settings.maestro_base_url or "").strip():
        return {"success": False, "message": "Maestro Base URL is not configured."}
    if not settings.api_key:
        return {"success": False, "message": "API Key must be saved before testing."}

    try:
        resp = MaestroClient(settings).health()
    except requests.exceptions.Timeout:
        return {"success": False, "message": "Connection to Maestro timed out."}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": "Could not reach Maestro at the configured URL."}
    except Exception as e:
        return {"success": False, "message": f"Connection error: {str(e)[:200]}"}

    if resp.status_code == 401:
        return {"success": False, "message": "API key rejected by Maestro (401)."}
    if resp.status_code == 404:
        return {
            "success": False,
            "message": "Maestro health endpoint not found (404) — check the Base URL / deploy.",
        }
    if resp.status_code != 200:
        return {"success": False, "message": f"Maestro returned HTTP {resp.status_code}."}

    try:
        data = resp.json()
    except Exception:
        data = {}

    if data.get("ok") and data.get("authenticated"):
        return {"success": True, "message": "Connected to Maestro."}
    if data.get("ok"):
        return {"success": False, "message": "Reached Maestro but the API key was not recognised."}
    return {"success": False, "message": "Unexpected response from Maestro."}
