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

import hashlib
import hmac
import re
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from ..catalog import load_catalog
from ..recommend import recommend_products
from ..config import Settings, load_settings
from ..delivery import Dispatcher
from ..env import load_dotenv
from ..voice import embed as voice_embed, merge as voice_merge
from ..ingestion import ConsentRequired, IngestionService, ValidationError
from ..live import LiveSessionManager
from ..queueing import JobQueue
from ..security import (
    AudioVault,
    check_webhook_url,
    issue_session_token,
    verify_session_token,
)
from ..store import Store
from ..whatsapp import WhatsAppQueue

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
    load_dotenv()  # pick up SARVAM_API_KEY / AWS creds from a local .env
    settings = settings or load_settings()
    data_dir = Path(data_dir or settings.data_dir)
    store = Store(data_dir / "voclyp.db")
    queue = JobQueue(data_dir / "queue.db")
    vault = AudioVault(settings.master_key)
    whatsapp_queue = WhatsAppQueue(data_dir / "whatsapp.db")
    ingestion = IngestionService(store, queue, data_dir / "audio", vault, settings)
    live_sessions = LiveSessionManager(store, ingestion, data_dir / "sessions")

    # Console session-token signing secret. Precedence:
    #   1. an explicit VOCLYP_SESSION_SECRET (production)
    #   2. derived from the master key via HMAC domain separation, so the
    #      token-signing key is NOT the raw audio-encryption key
    #   3. an ephemeral per-process secret (dev only; logs everyone out on
    #      restart). In production this path fails closed.
    if settings.session_secret:
        session_secret = settings.session_secret
    elif settings.master_key:
        session_secret = hmac.new(
            settings.master_key, b"voclyp/session-token/v1", hashlib.sha256
        ).digest()
    elif settings.env == "production":
        raise RuntimeError(
            "refusing to start in production without VOCLYP_SESSION_SECRET "
            "(or VOCLYP_MASTER_KEY) — session tokens would be unsigned-by-default"
        )
    else:
        session_secret = secrets.token_bytes(32)
    SESSION_TTL_S = 12 * 3600

    # role -> API scopes. The signed role claim is the source of truth, so a
    # console user can only do what their role permits, server-side.
    ROLE_SCOPES = {
        "admin": ("read", "admin"),
        "area_manager": ("read", "admin"),
        "store_manager": ("read", "admin"),
        "manager": ("read", "admin"),  # legacy web console
        "sales": ("ingest", "read"),
    }

    app = FastAPI(title="VoClyp Gateway", version="0.2.0")
    app.state.store, app.state.queue, app.state.vault = store, queue, vault
    app.state.whatsapp_queue = whatsapp_queue
    app.state.live_sessions = live_sessions
    app.state.rate_buckets = {}
    app.state.login_attempts = {}

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

    def _session_claims(authorization: str) -> dict | None:
        """Verify a Bearer session token AND re-check it against live user state
        (existence, current role, session epoch) so revoked or role-changed
        tokens stop working immediately — the token alone is never trusted."""
        prefix = "Bearer "
        if not (authorization or "").startswith(prefix):
            return None
        claims = verify_session_token(authorization[len(prefix):], session_secret)
        if claims is None:
            return None
        user = store.get_user(claims.get("sub", ""))
        if user is None:
            return None
        if claims.get("epoch") != user["session_epoch"]:
            return None  # revoked (logout-all / role change / password reset)
        if claims.get("role") != user["role"]:
            return None  # role changed since the token was issued
        return {**claims, "tenant": user["tenant_id"], "role": user["role"]}

    def current_user(authorization: str = Header(None)) -> dict:
        claims = _session_claims(authorization)
        if claims is None:
            raise HTTPException(401, "not authenticated")
        return claims

    def principal(x_api_key: str = Header(None),
                  authorization: str = Header(None)) -> dict:
        """A request is authorized by EITHER a tenant API key (machine clients)
        OR a console session token (logged-in users). Both resolve to a tenant
        and a scope set; downstream authorization is scope-based and identical."""
        if x_api_key:
            auth = store.authenticate(x_api_key)
            if auth is None:
                raise HTTPException(401, "invalid, expired, or revoked API key")
            _rate_limit("key:" + auth["key_id"])
            return {"tenant_id": auth["tenant_id"], "scopes": list(auth["scopes"]),
                    "subject": "key:" + auth["key_id"]}
        claims = _session_claims(authorization)
        if claims is not None:
            _rate_limit("user:" + claims["sub"])
            return {"tenant_id": claims["tenant"],
                    "scopes": list(ROLE_SCOPES.get(claims["role"], ())),
                    "role": claims["role"], "user_id": claims["sub"],
                    "subject": "user:" + claims["sub"]}
        raise HTTPException(401, "authentication required (API key or session)")

    def require(scope: str):
        def checker(auth: dict = Depends(principal)) -> dict:
            if scope not in auth["scopes"]:
                raise HTTPException(403, f"not permitted: missing '{scope}' scope")
            return auth
        return checker

    def _scoped_filters(auth: dict) -> dict:
        """Resolve area_id / store_ids for manager roles."""
        if auth.get("subject", "").startswith("key:"):
            return {"area_id": None, "store_ids": None}
        scope = store.get_user_role_scope(auth["tenant_id"], auth.get("user_id", ""))
        if not scope:
            return {"area_id": None, "store_ids": None}
        return {"area_id": scope.get("area_id"), "store_ids": scope.get("store_ids") or None}

    # -- console authentication (email/password, signed role token) ----------
    def _slug(text: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
        return s[:63] if re.match(r"^[a-z0-9][a-z0-9-]{1,62}$", s[:63]) else ""

    def _login_throttle(request: Request, email: str):
        # Cheap brute-force brake: cap attempts per (client, email) per window.
        ident = f"{request.client.host if request.client else '?'}:{email}"
        now = time.monotonic()
        attempts = app.state.login_attempts.setdefault(ident, [])
        attempts[:] = [t for t in attempts if now - t < 300]
        if len(attempts) >= 10:
            raise HTTPException(429, "too many login attempts; try again later",
                                headers={"Retry-After": "300"})
        attempts.append(now)

    def _session_payload(user: dict) -> dict:
        claims = {
            "sub": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "tenant": user["tenant_id"],
            "epoch": user["session_epoch"],  # revocation marker
            "iat": int(time.time()),
        }
        token = issue_session_token(claims, session_secret, SESSION_TTL_S)
        return {"token": token, "user": {k: claims[k] for k in
                ("email", "name", "role", "tenant")}
                | {"user_id": claims["sub"]}}

    @app.post("/auth/signup", status_code=201)
    async def signup(request: Request):
        body = await request.json()
        org = str(body.get("org", "") or "VoClyp Demo")
        tenant_id = _slug(org) or "voclyp-demo"
        email = str(body.get("email", ""))

        if store.tenant_industry(tenant_id) is None:
            # First account for a brand-new org becomes its manager/owner.
            store.create_tenant(tenant_id, org.strip() or "VoClyp Demo", "fmcg")
            role = "manager"
        elif store.tenant_user_count(tenant_id) == 0:
            role = "manager"  # seeded tenant, first human owns it
        else:
            # Joining an existing team requires a manager-issued invite; the
            # invite fixes the role, so no one can self-elect to manager.
            role = store.consume_invite(str(body.get("invite", "")), tenant_id)
            if role is None:
                raise HTTPException(
                    403, "joining this organization requires a valid invite")
        try:
            user_id = store.create_user(email, body.get("name", ""), role,
                                        tenant_id, str(body.get("password", "")))
            user = store.verify_user_password(email, str(body.get("password", "")))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        store.audit(tenant_id, None, "user_signup", f"user={user_id} role={role}")
        return _session_payload(user)

    @app.post("/auth/login")
    async def login(request: Request):
        body = await request.json()
        email = str(body.get("email", ""))
        _login_throttle(request, email.strip().lower())
        user = store.verify_user_password(email, str(body.get("password", "")))
        if user is None:
            raise HTTPException(401, "invalid email or password")
        store.audit(user["tenant_id"], None, "user_login", f"user={user['user_id']}")
        return _session_payload(user)

    @app.post("/auth/logout")
    def logout(claims: dict = Depends(current_user)):
        # Server-side logout: invalidate every outstanding token for this user.
        store.bump_session_epoch(claims["sub"])
        store.audit(claims["tenant"], None, "user_logout", f"user={claims['sub']}")
        return {"ok": True}

    @app.get("/auth/me")
    def auth_me(claims: dict = Depends(current_user)):
        return {"user": {k: claims.get(k) for k in ("email", "name", "role", "tenant")}
                | {"user_id": claims.get("sub")}}

    @app.post("/auth/invite", status_code=201)
    async def make_invite(request: Request, claims: dict = Depends(current_user)):
        # Only a manager may invite teammates, and only into their own tenant.
        if claims["role"] not in ("manager", "admin", "area_manager"):
            raise HTTPException(403, "not permitted to create invites")
        body = await request.json()
        try:
            code = store.create_invite(
                claims["tenant"], str(body.get("role", "sales")), claims["sub"])
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        store.audit(claims["tenant"], None, "invite_created",
                    f"by={claims['sub']} role={body.get('role', 'sales')}")
        return {"invite": code, "tenant": claims["tenant"]}

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
            "store_id": form.get("store_id", ""),
            "customer_phone": form.get("customer_phone", ""),
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

    @app.get("/v1/conversations/{conversation_id}/status")
    def conversation_status(conversation_id: str, auth: dict = Depends(require("read"))):
        tenant_id = auth["tenant_id"]
        if store.get_insight(tenant_id, conversation_id):
            return {"status": "ready"}
        job = queue.lookup(tenant_id, conversation_id)
        if job and job["status"] == "dead":
            detail = store.latest_audit_detail(
                tenant_id, conversation_id, "processing_failed",
            ) or ""
            err = detail.split(" -> ")[0].strip() if detail else "Processing failed"
            return {"status": "failed", "error": err}
        if job:
            return {"status": "processing", "attempts": job["attempts"]}
        return {"status": "processing"}

    @app.delete("/v1/conversations/{conversation_id}")
    def delete_on_demand(conversation_id: str, auth: dict = Depends(require("admin"))):
        return {"deleted": store.delete_conversation(auth["tenant_id"], conversation_id)}

    # -- stores & areas (multi-store support) --------------------------------
    @app.post("/v1/stores", status_code=201)
    async def create_store_endpoint(request: Request, auth: dict = Depends(require("admin"))):
        """Create a new store. Requires admin scope."""
        body = await request.json()
        store_id = str(body.get("store_id", ""))
        if not store_id:
            raise HTTPException(400, "store_id is required")
        try:
            created = store.create_store(
                auth["tenant_id"],
                store_id,
                str(body.get("name", "Unnamed Store")),
                str(body.get("area_id", "")),
                str(body.get("manager_id", "")),
                region=body.get("region"),
                lat=body.get("latitude"),
                lng=body.get("longitude"),
                address_full=body.get("address"),
                team_size=body.get("team_size"),
            )
            if not created:
                raise HTTPException(409, "store already exists")
            store.audit(auth["tenant_id"], None, "store_created", f"store={store_id}")
            return {"store_id": store_id, "status": "created"}
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @app.get("/v1/stores/{store_id}")
    def get_store_endpoint(store_id: str, auth: dict = Depends(require("read"))):
        """Get store details."""
        result = store.get_store(auth["tenant_id"], store_id)
        if not result:
            raise HTTPException(404, "store not found")
        return result

    @app.get("/v1/stores")
    def list_stores_endpoint(
        area_id: str = None, status: str = "active",
        auth: dict = Depends(require("read"))
    ):
        """List stores for the authenticated tenant."""
        return {"stores": store.list_stores(auth["tenant_id"], area_id=area_id, status=status)}

    @app.post("/v1/areas", status_code=201)
    async def create_area_endpoint(request: Request, auth: dict = Depends(require("admin"))):
        """Create a new area. Requires admin scope."""
        body = await request.json()
        area_id = str(body.get("area_id", ""))
        if not area_id:
            raise HTTPException(400, "area_id is required")
        try:
            created = store.create_area(
                auth["tenant_id"],
                area_id,
                str(body.get("name", "Unnamed Area")),
                str(body.get("manager_id", "")),
                region=body.get("region"),
            )
            if not created:
                raise HTTPException(409, "area already exists")
            store.audit(auth["tenant_id"], None, "area_created", f"area={area_id}")
            return {"area_id": area_id, "status": "created"}
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @app.get("/v1/areas/{area_id}")
    def get_area_endpoint(area_id: str, auth: dict = Depends(require("read"))):
        """Get area details."""
        result = store.get_area(auth["tenant_id"], area_id)
        if not result:
            raise HTTPException(404, "area not found")
        return result

    @app.get("/v1/areas")
    def list_areas_endpoint(auth: dict = Depends(require("read"))):
        """List areas for the authenticated tenant."""
        return {"areas": store.list_areas(auth["tenant_id"])}

    # -- live sessions (streaming field visits) --------------------------------
    @app.post("/v1/sessions", status_code=201)
    async def start_session(request: Request, auth: dict = Depends(require("ingest"))):
        body = await request.json()
        store_id = str(body.get("store_id", ""))
        agent_id = str(body.get("agent_id") or auth.get("user_id") or "agent-001")
        if not store_id:
            raise HTTPException(400, "store_id is required")
        result = live_sessions.start(auth["tenant_id"], store_id, agent_id)
        return {
            **result,
            "ws_url": f"/v1/sessions/{result['session_id']}/stream",
        }

    @app.get("/v1/sessions/active")
    def list_active_sessions(
        area_id: str = None,
        auth: dict = Depends(require("read")),
    ):
        scoped = _scoped_filters(auth)
        return {
            "sessions": store.list_active_sessions(
                auth["tenant_id"],
                area_id=area_id or scoped.get("area_id"),
                store_ids=scoped.get("store_ids"),
            ),
        }

    @app.get("/v1/sessions/{session_id}")
    def get_session(session_id: str, auth: dict = Depends(require("read"))):
        doc = live_sessions.get(auth["tenant_id"], session_id)
        if not doc:
            raise HTTPException(404, "session not found")
        return doc

    @app.patch("/v1/sessions/{session_id}")
    async def patch_session(session_id: str, request: Request,
                            auth: dict = Depends(require("ingest"))):
        body = await request.json()
        doc = live_sessions.patch_customer(
            auth["tenant_id"], session_id,
            name=body.get("customer_name"),
            phone=body.get("customer_phone"),
            source="manual",
        )
        if not doc:
            raise HTTPException(404, "session not found")
        return doc

    @app.post("/v1/sessions/{session_id}/consent")
    def consent_session(session_id: str, auth: dict = Depends(require("ingest"))):
        doc = live_sessions.consent(auth["tenant_id"], session_id)
        if not doc:
            raise HTTPException(404, "session not found")
        return doc

    @app.post("/v1/sessions/{session_id}/complete", status_code=202)
    async def complete_session(
        session_id: str,
        request: Request,
        auth: dict = Depends(require("ingest")),
    ):
        final_audio = None
        ctype = (request.headers.get("content-type") or "").lower()
        if "multipart/form-data" in ctype:
            form = await request.form()
            upload = form.get("audio")
            if upload is not None:
                final_audio = await upload.read()
        try:
            return live_sessions.complete(
                auth["tenant_id"], session_id, final_audio=final_audio,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.websocket("/v1/sessions/{session_id}/stream")
    async def session_stream(websocket: WebSocket, session_id: str, token: str = ""):
        await websocket.accept()
        claims = verify_session_token(token, session_secret) if token else None
        if claims is None:
            await websocket.close(code=4401)
            return
        user = store.get_user(claims.get("sub", ""))
        if user is None:
            await websocket.close(code=4401)
            return
        tenant_id = user["tenant_id"]
        session = live_sessions.get(tenant_id, session_id)
        if not session:
            await websocket.close(code=4404)
            return
        # A fresh connection means the rep (re)started voice assist — wipe any
        # stale transcript so the new listen starts clean and corrections aren't
        # fighting an old mis-hear.
        live_sessions.reset_asr(tenant_id, session_id)
        await websocket.send_json({"type": "reset"})
        seq = 0
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                if message.get("bytes"):
                    seq += 1
                    events = live_sessions.process_chunk(
                        tenant_id, session_id, seq, message["bytes"],
                    )
                    for ev in events:
                        await websocket.send_json(ev)
                elif message.get("text"):
                    import json as _json
                    try:
                        ctrl = _json.loads(message["text"])
                        if ctrl.get("type") == "ping":
                            await websocket.send_json({"type": "pong"})
                        elif ctrl.get("type") == "reset":
                            live_sessions.reset_asr(tenant_id, session_id)
                            await websocket.send_json({"type": "reset"})
                    except _json.JSONDecodeError:
                        pass
        except WebSocketDisconnect:
            return

    # -- analytics (area / store manager) --------------------------------------
    @app.get("/v1/analytics/stores/compare")
    def analytics_compare(
        area_id: str = None, period: str = "week",
        auth: dict = Depends(require("read")),
    ):
        scoped = _scoped_filters(auth)
        return store.analytics_stores_compare(
            auth["tenant_id"],
            area_id=area_id or scoped.get("area_id"),
            store_ids=scoped.get("store_ids"),
        )

    @app.get("/v1/analytics/stores/{store_id}")
    def analytics_store(store_id: str, auth: dict = Depends(require("read"))):
        detail = store.analytics_store_detail(auth["tenant_id"], store_id)
        if not detail:
            raise HTTPException(404, "store not found")
        return detail

    @app.get("/v1/analytics/summary")
    def analytics_summary(area_id: str = None, auth: dict = Depends(require("read"))):
        """Headline KPIs across the manager's scope (dashboard hero row)."""
        scoped = _scoped_filters(auth)
        return store.analytics_area_summary(
            auth["tenant_id"],
            area_id=area_id or scoped.get("area_id"),
            store_ids=scoped.get("store_ids"),
        )

    @app.get("/v1/analytics/reps")
    def analytics_reps(area_id: str = None, auth: dict = Depends(require("read"))):
        """Per-rep leaderboard (visits, avg score, win rate, top objection)."""
        scoped = _scoped_filters(auth)
        return store.analytics_reps(
            auth["tenant_id"],
            area_id=area_id or scoped.get("area_id"),
            store_ids=scoped.get("store_ids"),
        )

    # -- voice enrollment (rep voiceprint for diarization) ---------------------
    @app.post("/v1/voiceprints/enroll", status_code=201)
    async def enroll_voiceprint(audio: UploadFile, auth: dict = Depends(require("ingest"))):
        """Enroll (or refine) the logged-in rep's voiceprint from a short clip.
        The clip is fingerprinted and immediately discarded — only the feature
        vector is stored, keyed to the rep's user id."""
        user_id = auth.get("user_id")
        if not user_id:
            raise HTTPException(403, "voice enrollment requires a logged-in rep")
        body = await audio.read()
        if not body:
            raise HTTPException(400, "empty audio")
        result = voice_embed(body)
        existing = store.get_voiceprint(auth["tenant_id"], user_id)
        if existing:
            vector = voice_merge(existing["vector"], result["vector"],
                                 existing["sample_count"])
            samples = existing["sample_count"] + 1
        else:
            vector, samples = result["vector"], 1
        store.set_voiceprint(auth["tenant_id"], user_id, vector,
                             result["model"], samples)
        return {"enrolled": True, "model": result["model"],
                "samples": samples, "dims": len(vector)}

    @app.get("/v1/voiceprints/me")
    def voiceprint_status(auth: dict = Depends(require("ingest"))):
        user_id = auth.get("user_id")
        if not user_id:
            return {"enrolled": False, "samples": 0}
        vp = store.get_voiceprint(auth["tenant_id"], user_id)
        return {"enrolled": bool(vp),
                "samples": vp["sample_count"] if vp else 0,
                "model": vp["model"] if vp else None,
                "updated_at": vp["updated_at"] if vp else None}

    @app.get("/v1/catalog")
    def get_catalog(auth: dict = Depends(require("read"))):
        industry = store.tenant_industry(auth["tenant_id"]) or "sleep_company"
        try:
            catalog = load_catalog(industry)
        except FileNotFoundError:
            raise HTTPException(404, f"no catalog for industry {industry}")
        return catalog

    @app.get("/v1/insights/{conversation_id}/recommendations")
    def insight_recommendations(conversation_id: str, auth: dict = Depends(require("read"))):
        doc = store.get_insight(auth["tenant_id"], conversation_id)
        if not doc:
            raise HTTPException(404, "insight not found")
        industry = store.tenant_industry(auth["tenant_id"]) or "sleep_company"
        catalog = load_catalog(industry)

        # Build a short transcript so the grounding LLM can personalise the "why".
        speaker_labels = {"agent": "Sales rep", "customer": "Customer"}
        transcript_lines = []
        for t in (doc.get("transcript") or []):
            who = speaker_labels.get(t.get("speaker"), t.get("speaker") or "")
            said = t.get("normalized_text") or t.get("text") or ""
            if said:
                transcript_lines.append(f"{who}: {said}")
        transcript = "\n".join(transcript_lines)

        # Optional LLM grounding when Sarvam is configured; otherwise deterministic.
        llm_client = None
        if settings.sarvam_api_key:
            try:
                from ..providers.sarvam import SarvamClient
                llm_client = SarvamClient(settings.sarvam_api_key)
            except Exception:
                llm_client = None

        # Resolve which mattresses the conversation actually referenced
        # (named once, then "ye / isme / iska") so the discussed one leads.
        from ..product_mentions import resolve_product_mentions
        mentions = resolve_product_mentions(catalog, doc.get("transcript") or [])

        products = recommend_products(
            catalog, doc.get("signals") or [], transcript=transcript,
            llm_client=llm_client, discussed_skus=mentions["ordered"],
        )
        return {"conversation_id": conversation_id, "products": products}

    @app.post("/auth/users/{user_id}/role")
    async def set_user_role(
        user_id: str, request: Request, auth: dict = Depends(require("admin"))
    ):
        """Set a user's role and scope (for area managers)."""
        body = await request.json()
        role = str(body.get("role", "sales"))
        if role not in store.USER_ROLES:
            raise HTTPException(400, f"invalid role: {role}")
        store.set_user_role_scope(
            auth["tenant_id"],
            user_id,
            role,
            area_id=body.get("area_id"),
            store_ids=body.get("store_ids"),
        )
        store.audit(auth["tenant_id"], None, "user_role_updated",
                   f"user={user_id} role={role}")
        return {"user_id": user_id, "role": role, "updated": True}

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

    # -- WhatsApp recommendations (product sharing) ----------------------------
    @app.post("/v1/recommendations/whatsapp-send", status_code=202)
    async def send_whatsapp_recommendation(
        request: Request, auth: dict = Depends(require("ingest"))
    ):
        """Queue a WhatsApp product recommendation for delivery.

        The rep can optionally modify the message before sending.
        Status 202 indicates the message is queued; check /v1/recommendations/{message_id}
        for delivery status.
        """
        body = await request.json()
        customer_phone = str(body.get("customer_phone", ""))
        if not customer_phone:
            raise HTTPException(400, "customer_phone is required")

        conversation_id = str(body.get("conversation_id", ""))
        products = body.get("products") or []
        rep_name = body.get("rep_name", "Sales Rep")
        message_template = body.get("message_template", "default")
        message_body = str(body.get("message_body", ""))

        # Default template if not provided
        if not message_body and message_template == "default":
            brand = "The Sleep Company"
            product_lines = "\n".join([
                f"• {p.get('name', 'Product')} — ₹{p.get('price', 0)}"
                for p in products
            ])
            message_body = (
                f"Hi from {brand}!\n\nBased on our visit today, I recommend:\n\n"
                f"{product_lines}\n\n"
                f"Reply here for trial, EMI, or home delivery options."
            )

        message_id = whatsapp_queue.queue_message(
            auth["tenant_id"],
            conversation_id,
            customer_phone,
            products,
            message_body,
            rep_name=rep_name,
        )
        store.audit(auth["tenant_id"], conversation_id, "whatsapp_recommendation_queued",
                   f"message_id={message_id} customer={customer_phone}")
        return {
            "message_id": message_id,
            "status": "queued",
            "customer_phone": customer_phone,
            "created_at": whatsapp_queue.get_message(message_id)["created_at"],
        }

    @app.get("/v1/recommendations/{message_id}")
    def get_recommendation_status(
        message_id: str, auth: dict = Depends(require("read"))
    ):
        """Get delivery status of a WhatsApp recommendation."""
        msg = whatsapp_queue.get_message(message_id)
        if not msg or msg["tenant_id"] != auth["tenant_id"]:
            raise HTTPException(404, "message not found")
        return msg

    @app.get("/v1/recommendations")
    def list_recommendations(
        customer_phone: str = None,
        auth: dict = Depends(require("read")),
    ):
        """List recommendations sent to a customer."""
        if not customer_phone:
            raise HTTPException(400, "customer_phone is required")
        return {
            "customer_phone": customer_phone,
            "recommendations": whatsapp_queue.list_messages_for_customer(customer_phone),
        }

    # -- enterprise cloud layer (additive, off by default) -------------------
    # Mounted only when VOCLYP_ENTERPRISE_ENABLED is set. With the flag off the
    # gateway behaves exactly as before and never imports cloud SDKs.
    try:
        from ..enterprise.config import load_enterprise_settings

        ent_settings = load_enterprise_settings()
        if ent_settings.enabled:
            from ..enterprise.router import mount_enterprise

            mount_enterprise(app, require, ent_settings)
            app.state.enterprise_enabled = True
    except Exception as exc:  # never let the optional layer break the demo
        app.state.enterprise_enabled = False
        app.state.enterprise_error = f"{type(exc).__name__}: {exc}"

    return app


app = create_app()
