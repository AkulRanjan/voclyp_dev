"""HubSpot CRM channel — PLANNED connector (stub).

Mirrors the ZohoClient interface so it can be dropped into the routing
dispatcher's ``clients`` map (see voclyp/enterprise/runner.py) without any other
change. Offline mode records the would-be CRM write to the local sink. Live mode
is intentionally not implemented yet — wire the HubSpot CRM v3 contact/deal
upsert when this connector is turned on.

``send`` returns ``{"ok": bool, "response": dict, "detail": str}``.
"""
from __future__ import annotations

from . import _sink


class HubSpotClient:
    channel = "hubspot"

    def __init__(self, settings, live: bool):
        self.settings = settings
        self.live = live

    def send(self, payload: dict, idempotency_key: str = "") -> dict:
        if not self.live:
            entry = _sink.record(self.settings.local_path, "hubspot",
                                 dict(payload, idempotency_key=idempotency_key))
            return {"ok": True,
                    "response": {"mock": True, "id": entry["recorded_at"],
                                 "idempotency_key": idempotency_key},
                    "detail": "recorded to offline sink"}
        return self._send_live(payload, idempotency_key)

    def _send_live(self, payload: dict, idempotency_key: str = "") -> dict:  # pragma: no cover - planned
        # TODO: POST to https://api.hubapi.com/crm/v3/objects/contacts with a
        # private-app bearer token; associate a note with the extraction summary.
        # Use idempotency_key to dedupe retried writes during partial failures.
        return {"ok": False, "response": {},
                "detail": "hubspot live mode not implemented yet"}
