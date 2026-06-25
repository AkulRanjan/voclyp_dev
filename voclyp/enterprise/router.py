"""Flag-gated enterprise HTTP surface.

``mount_enterprise(app, require)`` is called from gateway/app.py only when
``EnterpriseSettings.enabled`` is true. It builds the pipeline once and exposes:

  POST /v1/enterprise/conversations               consent-first ingestion
  GET  /v1/enterprise/conversations/{id}          status + result
  POST /v1/enterprise/conversations/{id}/verify   release EMI WhatsApp hold
  GET  /v1/enterprise/verifications               agent verification queue
  POST /v1/enterprise/maintenance/routing         retry due outbox rows (admin)
  POST /v1/enterprise/maintenance/erasure         run erasure sweep (admin)

Everything is tenant-scoped from the authenticated principal.
"""
from __future__ import annotations

import json

from fastapi import Depends, HTTPException, Request, UploadFile

from .config import load_enterprise_settings
from .consent.service import ConsentError
from .obs import get_logger
from .pipeline import build_enterprise
from .store import open_async_store, schema_for_tenant

_log = get_logger("gateway")


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _public_conversation(conv: dict) -> dict:
    """Strip internal storage detail before returning to a client."""
    return {
        "id": conv["id"],
        "state": conv["state"],
        "store_id": conv.get("store_id"),
        "agent_id": conv.get("agent_id"),
        "duration_seconds": conv.get("duration_seconds"),
        "detected_languages": conv.get("detected_languages") or [],
        "asr_path": conv.get("asr_path"),
        "transcript_codemix": conv.get("transcript_codemix"),
        "transcript_english": conv.get("transcript_english"),
        "extraction": conv.get("extraction"),
        "extraction_confidence": conv.get("extraction_confidence"),
        "requires_human_verification": bool(conv.get("requires_human_verification")),
        "verified_by": conv.get("verified_by"),
        "verified_at": conv.get("verified_at"),
        "erase_after": conv.get("erase_after"),
        "erased_at": conv.get("erased_at"),
        "error_detail": conv.get("error_detail"),
        "created_at": conv.get("created_at"),
        "updated_at": conv.get("updated_at"),
    }


def mount_enterprise(app, require, settings=None) -> None:
    settings = settings or load_enterprise_settings()
    pipeline = build_enterprise(settings)
    app.state.enterprise = pipeline
    # async psycopg pool for schema-routed reads + the orphan sweep (None offline)
    app.state.enterprise_async = open_async_store(settings)

    @app.middleware("http")
    async def tenant_search_path(request: Request, call_next):
        """Identify the tenant from the API key and bind the request to that
        tenant's PostgreSQL schema (search_path) for its whole duration. The
        async store applies the SET on each connection it borrows for the
        request; offline this only stamps the resolved schema for handlers."""
        if request.url.path.startswith("/v1/enterprise"):
            api_key = request.headers.get("x-api-key")
            tenant_id = None
            if api_key:
                auth = app.state.store.authenticate(api_key)
                if auth:
                    tenant_id = auth["tenant_id"]
            if tenant_id:
                request.state.tenant_id = tenant_id
                request.state.tenant_schema = schema_for_tenant(tenant_id)
        return await call_next(request)

    @app.post("/v1/enterprise/conversations", status_code=202)
    async def enterprise_ingest(request: Request, audio: UploadFile,
                                auth: dict = Depends(require("ingest"))):
        form = await request.form()
        purposes = {
            "recording": _truthy(form.get("consent_recording", "false")),
            "whatsapp_followup": _truthy(form.get("consent_whatsapp", "false")),
            "crm_storage": _truthy(form.get("consent_crm", "false")),
            "marketing": _truthy(form.get("consent_marketing", "false")),
        }
        device_fingerprint = {}
        raw_fp = form.get("device_fingerprint", "")
        if raw_fp:
            try:
                device_fingerprint = json.loads(raw_fp)
            except (json.JSONDecodeError, TypeError):
                device_fingerprint = {"raw": str(raw_fp)}

        body = await audio.read()
        if not body:
            raise HTTPException(400, "empty audio upload")
        try:
            result = pipeline.ingestion.ingest(
                tenant_id=auth["tenant_id"],
                agent_id=form.get("agent_id", auth.get("user_id", "")),
                store_id=form.get("store_id", ""),
                session_id=form.get("session_id", ""),
                language=form.get("language", "hi-IN"),
                purposes=purposes,
                device_fingerprint=device_fingerprint,
                notice_text=form.get("notice_text", ""),
                audio=body,
                customer_phone=form.get("customer_phone", ""),
                mock_transcript=form.get("mock_transcript") or None,
            )
        except ConsentError as exc:
            raise HTTPException(422, f"consent required: {exc}")
        return result

    @app.get("/v1/enterprise/conversations/{conversation_id}")
    def enterprise_get(conversation_id: str, auth: dict = Depends(require("read"))):
        conv = pipeline.store.get_conversation(conversation_id, auth["tenant_id"])
        if conv is None:
            raise HTTPException(404, "conversation not found")
        out = _public_conversation(conv)
        out["routing"] = [
            {"channel": r["channel"], "status": r["status"], "attempts": r["attempts"],
             "detail": r.get("detail")}
            for r in pipeline.store.get_routing_for_conversation(conversation_id)
        ]
        return out

    @app.post("/v1/enterprise/conversations/{conversation_id}/verify")
    async def enterprise_verify(conversation_id: str, request: Request,
                                auth: dict = Depends(require("ingest"))):
        conv = pipeline.store.get_conversation(conversation_id, auth["tenant_id"])
        if conv is None:
            raise HTTPException(404, "conversation not found")
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        verified_by = auth.get("user_id") or auth.get("subject") or "agent"
        result = pipeline.dispatcher.verify(
            conversation_id, verified_by=verified_by,
            whatsapp_to=str(payload.get("whatsapp_to", "")))
        return result

    @app.get("/v1/enterprise/verifications")
    def enterprise_verifications(agent_id: str = None,
                                 auth: dict = Depends(require("read"))):
        rows = pipeline.store.pending_verifications(auth["tenant_id"], agent_id)
        return {"pending": [_public_conversation(r) for r in rows]}

    @app.post("/v1/enterprise/tenants/{tenant_id}/provision", status_code=201)
    def enterprise_provision(tenant_id: str, auth: dict = Depends(require("admin"))):
        # tenants may only provision their own schema
        if tenant_id != auth["tenant_id"]:
            raise HTTPException(403, "may only provision your own tenant schema")
        schema = pipeline.store.provision_tenant(tenant_id)
        return {"tenant_id": tenant_id, "schema": schema, "provisioned": True}

    @app.post("/v1/enterprise/maintenance/routing")
    def enterprise_routing_retry(auth: dict = Depends(require("admin"))):
        return {"processed": pipeline.dispatcher.process_due()}

    @app.post("/v1/enterprise/maintenance/erasure")
    def enterprise_erasure_run(auth: dict = Depends(require("admin"))):
        return pipeline.erasure.run_once()
