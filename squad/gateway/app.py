"""FastAPI gateway, bound to 127.0.0.1 only (rule 11).

Security: host check, strict CSP, CSRF on state-changing posts, short-lived
tokens, rate-limited login, escaped output, and a web page that can only
lower budgets / start saved templates / approve a short allowlist (installs and
credential actions stay terminal-only).
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from squad.gateway.auth import SessionStore
from squad.gateway.security import RateLimiter, escape_html
from squad.gateway.webauthn import (
    WebAuthnState,
    generate_authentication_options,
    generate_register_options,
    verify_authentication,
    verify_origin_and_host,
    verify_registration,
    webauthn_available,
)

ALLOWED_HOSTS = ("127.0.0.1", "localhost")
_CSP = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
# The web page may approve only this short allowlist of Tier-2 actions;
# installs and credential actions stay terminal-only.
APPROVABLE_ACTIONS: tuple[str, ...] = ()


class _ApproveBody(BaseModel):
    action: str
    approval_id: str


class _BudgetBody(BaseModel):
    cap: str
    value: float


class _StartBody(BaseModel):
    name: str


def create_app(
    controller,
    *,
    sessions=None,
    login_check=None,
    approvable_actions=APPROVABLE_ACTIONS,
    rate_limit: int = 20,
    rate_window: float = 60.0,
    allowed_hosts=ALLOWED_HOSTS,
    webauthn_state: WebAuthnState | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sessions = sessions or SessionStore()
    limiter = RateLimiter(limit=rate_limit, window_seconds=rate_window)
    login_check = login_check or (lambda: True)
    wa = webauthn_state or WebAuthnState()

    @app.middleware("http")
    async def security(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in allowed_hosts:
            return JSONResponse({"error": "forbidden host"}, status_code=403)
        if request.method == "POST":
            is_idle = getattr(controller, "is_idle", None)
            if is_idle is not None and is_idle():
                return JSONResponse({"error": "gateway off (idle)"}, status_code=503)
        touch = getattr(controller, "touch", None)
        if touch is not None:
            touch()
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def require_auth(authorization: str | None) -> None:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing token")
        token = authorization[len("Bearer ") :]
        if not sessions.valid(token):
            raise HTTPException(401, "invalid or expired token")

    def require_csrf(x_csrf_token: str | None) -> None:
        if not x_csrf_token:
            raise HTTPException(403, "missing CSRF token")

    @app.get("/", response_class=HTMLResponse)
    def home():
        return "<h1>squad remote</h1><p>login via POST /api/login</p>"

    @app.get("/api/webauthn/register-options")
    def webauthn_register_options():
        """Return WebAuthn registration options (challenge, rp, user)."""
        return generate_register_options(wa)

    @app.post("/api/webauthn/register")
    def webauthn_register(request: Request, body: dict):
        """Verify a WebAuthn registration response and store the credential."""
        if not verify_origin_and_host(
            request.headers.get("origin") or "", (request.headers.get("host") or "").split(":")[0]
        ):
            raise HTTPException(403, "bad origin or host")
        if not verify_registration(wa, body):
            raise HTTPException(400, "registration failed")
        return {"ok": True}

    @app.get("/api/webauthn/authenticate-options")
    def webauthn_authenticate_options():
        """Return WebAuthn authentication (login) options."""
        return generate_authentication_options(wa)

    @app.post("/api/login")
    def login(request: Request, body: dict | None = None):
        host = request.client.host if request.client else "unknown"
        if not limiter.allow(host):
            raise HTTPException(429, "rate limited")

        # Prefer WebAuthn passkey when available
        if webauthn_available() and body is not None:
            origin = request.headers.get("origin") or ""
            req_host = (request.headers.get("host") or "").split(":")[0]
            if not verify_origin_and_host(origin, req_host):
                raise HTTPException(403, "bad origin or host")
            if not verify_authentication(wa, body):
                raise HTTPException(401, "passkey verification failed")
        else:
            if not login_check():
                raise HTTPException(401, "login failed")

        token = sessions.issue()
        # Link this session to the run state so the gateway reflects live status.
        if getattr(controller, "attach_session", None):
            controller.attach_session(token)
        return {"token": token, "expires_in": sessions._ttl}

    @app.get("/api/status")
    def status(authorization: str | None = Header(None)):
        require_auth(authorization)
        data = controller.status()
        # Merge live agent cards + budget + approvals if present
        live = getattr(controller, "live_status", None)
        if live:
            try:
                live_data = live() if callable(live) else live
                if isinstance(live_data, dict):
                    data.update(live_data)
            except Exception:
                pass
        return data

    @app.post("/api/approve")
    def approve(
        body: _ApproveBody,
        authorization: str | None = Header(None),
        x_csrf_token: str | None = Header(None),
    ):
        require_auth(authorization)
        require_csrf(x_csrf_token)
        if body.action not in approvable_actions:
            raise HTTPException(
                403, f"action '{escape_html(body.action)}' is not approvable from the web page"
            )
        return {"approved": controller.approve(body.approval_id)}

    @app.post("/api/stop")
    def stop(
        authorization: str | None = Header(None),
        x_csrf_token: str | None = Header(None),
    ):
        require_auth(authorization)
        require_csrf(x_csrf_token)
        controller.stop()
        return {"stopped": True}

    @app.post("/api/budget")
    def budget_lower(
        body: _BudgetBody,
        authorization: str | None = Header(None),
        x_csrf_token: str | None = Header(None),
    ):
        require_auth(authorization)
        require_csrf(x_csrf_token)
        return {"lowered": controller.lower_budget(body.cap, body.value)}

    @app.get("/api/templates")
    def templates(authorization: str | None = Header(None)):
        require_auth(authorization)
        return {"templates": controller.templates}

    @app.post("/api/start")
    def start(
        body: _StartBody,
        authorization: str | None = Header(None),
        x_csrf_token: str | None = Header(None),
    ):
        require_auth(authorization)
        require_csrf(x_csrf_token)
        return {"started": controller.start_template(body.name)}

    return app
