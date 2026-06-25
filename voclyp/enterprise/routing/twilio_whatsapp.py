"""Twilio WhatsApp Business channel.

Live mode sends an approved content template via the Twilio REST API. Offline
mode records the would-be message to a local sink. WhatsApp is the channel
held behind human verification whenever EMI figures are present, so the
dispatcher only ever calls this client once a row is in 'pending' status.
"""
from __future__ import annotations

from . import _sink


class TwilioWhatsAppClient:
    channel = "whatsapp"

    def __init__(self, settings, live: bool):
        self.settings = settings
        self.live = live

    def send(self, payload: dict, idempotency_key: str = "") -> dict:
        if not self.live:
            entry = _sink.record(self.settings.local_path, "whatsapp",
                                 dict(payload, idempotency_key=idempotency_key))
            return {"ok": True, "response": {"mock": True, "sid": "SM" + entry["recorded_at"],
                                             "idempotency_key": idempotency_key},
                    "detail": "recorded to offline sink"}
        return self._send_live(payload, idempotency_key)

    def _send_live(self, payload: dict, idempotency_key: str = "") -> dict:  # pragma: no cover - needs Twilio
        try:
            from twilio.base.exceptions import TwilioRestException  # noqa: F401
            from twilio.http.http_client import TwilioHttpClient
            from twilio.rest import Client

            # inject Idempotency-Key on the underlying HTTP request so Twilio
            # drops duplicated retries during partial network failures
            http_client = TwilioHttpClient()
            if idempotency_key:
                http_client.session.headers.update({"Idempotency-Key": idempotency_key})
            client = Client(self.settings.twilio_account_sid,
                            self.settings.twilio_auth_token, http_client=http_client)
            to = payload.get("to") or ""
            if not to.startswith("whatsapp:"):
                to = "whatsapp:" + to
            kwargs = {"from_": self.settings.twilio_whatsapp_from, "to": to}
            if self.settings.twilio_template_sid and payload.get("content_variables"):
                kwargs["content_sid"] = self.settings.twilio_template_sid
                kwargs["content_variables"] = payload["content_variables"]
            else:
                kwargs["body"] = payload.get("body") or ""
            msg = client.messages.create(**kwargs)
            return {"ok": True, "response": {"sid": msg.sid, "status": msg.status},
                    "detail": "whatsapp sent"}
        except Exception as exc:
            return {"ok": False, "response": {}, "detail": f"{type(exc).__name__}: {exc}"}
