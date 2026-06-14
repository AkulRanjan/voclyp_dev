"""API gateway — the single way into the system.

Security controls at this boundary:
- Authentication: ``X-API-Key`` verified against salted hashes (constant
  time), with revocation and expiry; the key maps to exactly one tenant.
- Authorization: scopes per key (``ingest`` to upload, ``read`` to pull
  insights, ``admin`` for webhooks and delete-on-demand).
- Per-key rate limiting (429 + Retry-After).
- Upload size caps checked against Content-Length and again on the body.
- Webhook registration runs the SSRF guard (https-only, public addresses).
- Security headers on every response; errors never leak internals.
- TLS termination and network isolation are deployment concerns
  (see docs/SECURITY.md) — run this behind a TLS-terminating proxy.

Requires the gateway extras (`pip install fastapi uvicorn python-multipart`);
the rest of the platform has no third-party dependencies.

Run:  uvicorn voclyp.gateway.app:app  (set VOCLYP_DATA_DIR / VOCLYP_MASTER_KEY)
"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from ..config import Settings, load_settings
from ..delivery import Dispatcher
from ..ingestion import ConsentRequired, IngestionService, ValidationError
from ..queueing import JobQueue
from ..security import AudioVault, check_webhook_url
from ..store import Store

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'",
}

# The bundled demo web app (served under /app) needs same-origin scripts,
# styles, and API calls — but still no third-party origins, no inline code.
_WEBAPP_SECURITY_HEADERS = dict(_SECURITY_HEADERS, **{
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; media-src 'self' blob:"
    ),
})

_WEBAPP_DIR = Path(__file__).resolve().parent / "webapp"
_WEBAPP_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


def create_app(data_dir=None, settings: Settings = None) -> FastAPI:
    settings = settings or load_settings()
    data_dir = Path(data_dir or settings.data_dir)
    store = Store(data_dir / "voclyp.db")
    queue = JobQueue(data_dir / "queue.db")
    vault = AudioVault(settings.master_key)
    ingestion = IngestionService(store, queue, data_dir / "audio", vault, settings)

    app = FastAPI(title="VoClyp Gateway", version="0.2.0")
    app.state.store, app.state.queue, app.state.vault = store, queue, vault
    app.state.rate_buckets = {}

    @app.middleware("http")
    async def hardening(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and int(length) > settings.max_upload_bytes + 16384:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        response = await call_next(request)
        is_webapp = request.url.path == "/" or request.url.path.startswith("/app")
        response.headers.update(
            _WEBAPP_SECURITY_HEADERS if is_webapp else _SECURITY_HEADERS)
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        # Never leak stack traces or internal paths to callers.
        return JSONResponse({"detail": "internal error"}, status_code=500)

    def _rate_limit(key_id: str):
        now = time.monotonic()
        bucket = app.state.rate_buckets.setdefault(key_id, [])
        bucket[:] = [t for t in bucket if now - t < settings.rate_limit_window_s]
        if len(bucket) >= settings.rate_limit_requests:
            raise HTTPException(
                429, "rate limit exceeded",
                headers={"Retry-After": str(int(settings.rate_limit_window_s))},
            )
        bucket.append(now)

    def principal(x_api_key: str = Header(...)) -> dict:
        auth = store.authenticate(x_api_key)
        if auth is None:
            raise HTTPException(401, "invalid, expired, or revoked API key")
        _rate_limit(auth["key_id"])
        return auth

    def require(scope: str):
        def checker(auth: dict = Depends(principal)) -> dict:
            if scope not in auth["scopes"]:
                raise HTTPException(403, f"API key lacks the '{scope}' scope")
            return auth
        return checker

    # -- demo web app (static, same-origin, talks only to /v1) ---------------
    @app.get("/", include_in_schema=False)
    def webapp_root():
        return RedirectResponse("/app/")

    @app.get("/app/", include_in_schema=False)
    def webapp_index():
        return FileResponse(_WEBAPP_DIR / "index.html",
                            media_type=_WEBAPP_TYPES[".html"])

    @app.get("/app/{asset}", include_in_schema=False)
    def webapp_asset(asset: str):
        # Whitelist by extension and forbid any path component other than a
        # bare filename inside the webapp directory.
        target = _WEBAPP_DIR / asset
        if (Path(asset).name != asset
                or target.suffix not in _WEBAPP_TYPES
                or not target.is_file()):
            raise HTTPException(404, "not found")
        return FileResponse(target, media_type=_WEBAPP_TYPES[target.suffix])

    @app.post("/v1/conversations", status_code=202)
    async def submit_conversation(
        request: Request, audio: UploadFile, auth: dict = Depends(require("ingest"))
    ):
        form = await request.form()
        metadata = {
            "agent_id": form.get("agent_id", ""),
            "client_ref": form.get("client_ref", ""),
            "consent": {
                "captured": form.get("consent_captured") == "true",
                "customer_name": form.get("customer_name", ""),
            },
        }
        body = await audio.read()
        try:
            conversation_id = ingestion.submit(auth["tenant_id"], body, metadata)
        except ConsentRequired as exc:
            raise HTTPException(422, str(exc))
        except ValidationError as exc:
            raise HTTPException(400, str(exc))
        return {"conversation_id": conversation_id, "status": "queued"}

    @app.get("/v1/insights")
    def list_insights(auth: dict = Depends(require("read"))):
        return {"insights": store.list_insights(auth["tenant_id"])}

    @app.get("/v1/insights/{conversation_id}")
    def get_insight(conversation_id: str, auth: dict = Depends(require("read"))):
        doc = store.get_insight(auth["tenant_id"], conversation_id)
        if doc is None:
            raise HTTPException(404, "not found (or still processing)")
        return doc

    @app.delete("/v1/conversations/{conversation_id}")
    def delete_on_demand(conversation_id: str, auth: dict = Depends(require("admin"))):
        return {"deleted": store.delete_conversation(auth["tenant_id"], conversation_id)}

    @app.post("/v1/webhooks", status_code=201)
    async def register_webhook(request: Request, auth: dict = Depends(require("admin"))):
        body = await request.json()
        url = str(body.get("url", ""))
        event_types = body.get("event_types") or ["*"]
        if (not isinstance(event_types, list)
                or not all(isinstance(t, str) and t for t in event_types)):
            raise HTTPException(400, "event_types must be a list of strings")
        ok, reason = check_webhook_url(url, settings.allow_insecure_webhooks)
        if not ok:
            raise HTTPException(400, f"webhook rejected: {reason}")
        endpoint_id, secret = store.add_webhook(auth["tenant_id"], url, event_types)
        # The signing secret is returned exactly once; store it server-side.
        return {"endpoint_id": endpoint_id, "registered": url,
                "event_types": event_types, "signing_secret": secret}

    @app.get("/v1/webhooks")
    def list_webhooks(auth: dict = Depends(require("admin"))):
        """Endpoints with their delivery health (success rate, DLQ depth) —
        delivery health is a shared, visible SLO, not a support-ticket mystery."""
        return {"endpoints": store.list_endpoints(auth["tenant_id"]),
                "delivery_stats": store.delivery_stats(auth["tenant_id"])}

    @app.post("/v1/webhooks/{endpoint_id}/rotate")
    def rotate_webhook(endpoint_id: str, auth: dict = Depends(require("admin"))):
        """Dual-secret rotation: deliveries are signed with both secrets for
        the overlap window, so consumers switch at their own pace."""
        secret = store.rotate_webhook_secret(auth["tenant_id"], endpoint_id)
        if secret is None:
            raise HTTPException(404, "unknown endpoint")
        return {"endpoint_id": endpoint_id, "signing_secret": secret}

    @app.delete("/v1/webhooks/{endpoint_id}")
    def disable_webhook(endpoint_id: str, auth: dict = Depends(require("admin"))):
        if not store.set_endpoint_status(auth["tenant_id"], endpoint_id, "disabled"):
            raise HTTPException(404, "unknown endpoint")
        return {"endpoint_id": endpoint_id, "status": "disabled"}

    @app.post("/v1/webhooks/{endpoint_id}/test")
    def test_webhook(endpoint_id: str, auth: dict = Depends(require("admin"))):
        """Send a signed endpoint.test.ping so integrators can verify their
        receiver before real traffic arrives."""
        result = Dispatcher(store, settings).send_test_event(
            auth["tenant_id"], endpoint_id
        )
        if not result["sent"] and result.get("detail") == "unknown endpoint":
            raise HTTPException(404, "unknown endpoint")
        return result

    @app.get("/v1/deliveries")
    def list_deliveries(conversation_id: str = None, status: str = None,
                        auth: dict = Depends(require("admin"))):
        return {"deliveries": store.deliveries_for(
            auth["tenant_id"], conversation_id, status)}

    @app.post("/v1/deliveries/replay")
    async def replay_dlq(request: Request, auth: dict = Depends(require("admin"))):
        """One-click DLQ replay once the consumer endpoint has recovered;
        optionally scoped to a single endpoint via {"endpoint_id": ...}."""
        body = await request.json() if int(request.headers.get("content-length") or 0) else {}
        replayed = store.replay_dead(
            auth["tenant_id"], time.time(), body.get("endpoint_id"))
        Dispatcher(store, settings).deliver_due()
        return {"replayed": replayed}

    @app.post("/v1/insights/{conversation_id}/feedback", status_code=201)
    async def submit_feedback(conversation_id: str, request: Request,
                              auth: dict = Depends(require("read"))):
        """Correction from a user; flows back into future training (MLOps)."""
        if store.get_insight(auth["tenant_id"], conversation_id) is None:
            raise HTTPException(404, "not found")
        body = await request.json()
        target = str(body.get("target", ""))[:128]
        correction = str(body.get("correction", ""))[:1024]
        if not target or not correction:
            raise HTTPException(400, "both 'target' and 'correction' are required")
        store.add_feedback(auth["tenant_id"], conversation_id, target,
                           correction, str(body.get("note", ""))[:1024])
        return {"recorded": True}

    @app.get("/v1/metrics")
    def metrics(auth: dict = Depends(require("admin"))):
        return {"stages": store.metrics_summary(auth["tenant_id"]),
                "provider_usage": store.usage_summary(auth["tenant_id"]),
                "queue": queue.counts()}

    @app.get("/v1/audit")
    def audit_export(auth: dict = Depends(require("read"))):
        ok, bad_id = store.verify_audit_chain(auth["tenant_id"])
        return {"chain_intact": ok, "first_bad_entry": bad_id,
                "events": store.audit_export(auth["tenant_id"])}

    return app


app = create_app()
