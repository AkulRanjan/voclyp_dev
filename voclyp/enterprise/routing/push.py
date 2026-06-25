"""Agent push channel.

Notifies the sales agent's app — either a fresh insight is ready, or (when EMI
figures were detected) a 1-tap verification is required before WhatsApp goes
out. Offline mode records to a local sink; live mode POSTs to a configured
push webhook (FCM/APNs proxy) if one is provided.
"""
from __future__ import annotations

import json
import os
import urllib.request

from . import _sink


class PushClient:
    channel = "push"

    def __init__(self, settings, live: bool | None = None):
        self.settings = settings
        self.webhook = os.environ.get("VOCLYP_PUSH_WEBHOOK", "").strip()
        self.live = bool(self.webhook) if live is None else live

    def send(self, payload: dict, idempotency_key: str = "") -> dict:
        if not self.live:
            _sink.record(self.settings.local_path, "push",
                         dict(payload, idempotency_key=idempotency_key))
            return {"ok": True, "response": {"mock": True}, "detail": "recorded to offline sink"}
        return self._send_live(payload, idempotency_key)

    def _send_live(self, payload: dict, idempotency_key: str = "") -> dict:  # pragma: no cover - needs webhook
        try:
            body = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key
            req = urllib.request.Request(
                self.webhook, data=body, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return {"ok": 200 <= resp.status < 300, "response": {"status": resp.status},
                        "detail": "push delivered"}
        except Exception as exc:
            return {"ok": False, "response": {}, "detail": f"{type(exc).__name__}: {exc}"}
