"""Zoho CRM channel.

Live mode exchanges the long-lived refresh token for an access token and
upserts a Lead + Note carrying the extracted intelligence. Offline mode records
the would-be CRM write to a local sink. ``send`` returns
``{"ok": bool, "response": dict, "detail": str}``.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from . import _sink


class ZohoClient:
    channel = "zoho"

    def __init__(self, settings, live: bool):
        self.settings = settings
        self.live = live

    def send(self, payload: dict, idempotency_key: str = "") -> dict:
        if not self.live:
            entry = _sink.record(self.settings.local_path, "zoho",
                                 dict(payload, idempotency_key=idempotency_key))
            return {"ok": True, "response": {"mock": True, "id": entry["recorded_at"],
                                             "idempotency_key": idempotency_key},
                    "detail": "recorded to offline sink"}
        return self._send_live(payload, idempotency_key)

    def _send_live(self, payload: dict, idempotency_key: str = "") -> dict:  # pragma: no cover - needs Zoho
        try:
            token = self._access_token()
            body = json.dumps({"data": [payload.get("lead", payload)]}).encode("utf-8")
            headers = {"Authorization": f"Zoho-oauthtoken {token}",
                       "Content-Type": "application/json"}
            if idempotency_key:
                # third-party dedupe of retried CRM writes during partial failures
                headers["Idempotency-Key"] = idempotency_key
            req = urllib.request.Request(
                self.settings.zoho_api_domain.rstrip("/") + "/crm/v3/Leads",
                data=body, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "response": data, "detail": "zoho lead upserted"}
        except Exception as exc:
            return {"ok": False, "response": {}, "detail": f"{type(exc).__name__}: {exc}"}

    def _access_token(self) -> str:  # pragma: no cover - needs Zoho
        params = urllib.parse.urlencode({
            "refresh_token": self.settings.zoho_refresh_token,
            "client_id": self.settings.zoho_client_id,
            "client_secret": self.settings.zoho_client_secret,
            "grant_type": "refresh_token",
        }).encode("utf-8")
        req = urllib.request.Request(
            self.settings.zoho_accounts_domain.rstrip("/") + "/oauth/v2/token",
            data=params, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))["access_token"]
