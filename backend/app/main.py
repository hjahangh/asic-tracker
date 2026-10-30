"""FastAPI entry point. All writes are revision-checked, atomic transactions."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, event as sqlalchemy_event, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import Actor, actor_for_request, require_editor
from .config import Settings
from .domain import INVALID_TEXT, DomainError, requires_admin, validate_transition, validate_workspace
from .planning import allocation_plan, today_pacific, valid_date
from . import repository

log = logging.getLogger("asic_tracker")
EXPECTED_SCHEMA_REVISION = "20261029_0001"


class WorkspaceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, strict=True)
    state: dict
    reason: str = Field(default="Update workspace", min_length=1, max_length=200)
    operation: Literal["edit", "restore", "reset", "import"] = "edit"

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value):
        if isinstance(value, str):
            if INVALID_TEXT.search(value):
                raise ValueError("reason must contain valid Unicode without null characters.")
            return value.strip()
        return value


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            too_large = int(headers.get(b"content-length", b"0")) > self.max_bytes
        except ValueError:
            too_large = True
        if too_large:
            return await JSONResponse({"detail": {"code": "payload_too_large", "message": "The workspace exceeds the upload limit."}}, status_code=413)(scope, receive, send)
        if scope.get("method") not in {"PUT", "POST", "PATCH"}:
            return await self.app(scope, receive, send)
        # Bound chunked bodies before the framework parses JSON, rather than
        # depending on an optional or potentially forged Content-Length header.
        messages, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                return await JSONResponse({"detail": {"code": "payload_too_large", "message": "The workspace exceeds the upload limit."}}, status_code=413)(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break
        cursor = 0

        async def buffered_receive():
            nonlocal cursor
            if cursor < len(messages):
                message = messages[cursor]
                cursor += 1
                return message
            return await receive()

        await self.app(scope, buffered_receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = None
    if settings.database_url:
        options = {"pool_pre_ping": True}
        if settings.database_url.startswith("sqlite"):
            options.update(connect_args={"check_same_thread": False}, poolclass=StaticPool)
        engine = create_engine(settings.database_url, **options)
        if settings.database_url.startswith("sqlite"):
            @sqlalchemy_event.listens_for(engine, "connect")
            def sqlite_foreign_keys(dbapi_connection, connection_record):
                dbapi_connection.execute("PRAGMA foreign_keys=ON")
    factory = sessionmaker(bind=engine, expire_on_commit=False) if engine else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.validate()
        if settings.auth_mode == "development":
            log.warning("Development identity is enabled. Use only on a loopback-bound development deployment.")
        yield
        if engine is not None:
            engine.dispose()

    app = FastAPI(title="ASIC Tracker API", version="0.1.0", docs_url=None, redoc_url=None,
        openapi_url=None, lifespan=lifespan)
    app.state.settings, app.state.engine, app.state.session_factory = settings, engine, factory
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method in {"PUT", "POST", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin:
                try:
                    origin_host = urlsplit(origin).netloc.lower()
                except ValueError:
                    origin_host = ""
                if not origin_host or origin_host != request.headers.get("host", "").lower():
                    return JSONResponse({"detail": {"code": "cross_origin_write", "message": "Cross-origin writes are not allowed."}}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return JSONResponse({"detail": {"code": "invalid_workspace", "message": str(error), "errors": error.errors}}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, error: RequestValidationError):
        # Do not echo arbitrary input/exception context back through JSONResponse:
        # NaN or an unpaired surrogate in invalid input can itself break its
        # serializer, turning a normal validation failure into HTTP 500.
        def safe_text(value):
            return value.encode("utf-8", errors="backslashreplace").decode("utf-8") if isinstance(value, str) else value
        details = [{"type": safe_text(item["type"]), "loc": [safe_text(part) for part in item["loc"]],
                    "msg": safe_text(item["msg"])} for item in error.errors()]
        return JSONResponse({"detail": details}, status_code=422)

    @app.exception_handler(repository.RevisionConflict)
    async def revision_error(request: Request, error):
        return JSONResponse({"detail": {"code": "revision_conflict", "message": "Another user updated the workspace. Load the latest data and retry your change.", "current_revision": error.current_revision}}, status_code=409)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, error):
        log.warning("Workspace change rejected by a database integrity constraint.")
        return JSONResponse({"detail": {"code": "integrity_conflict", "message": "A database relationship or uniqueness rule rejected the change. No partial update was saved."}}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error):
        log.warning("Database operation failed (%s).", type(error).__name__)
        return JSONResponse({"detail": {"code": "database_unavailable", "message": "The database is unavailable. Retry after the hosting team checks the service."}}, status_code=503)

    def session_dependency():
        if factory is None:
            raise HTTPException(503, detail={"code": "database_unconfigured", "message": "Database configuration is missing."})
        with factory() as session:
            yield session

    @app.get("/health/live")
    @app.get("/api/health/live", include_in_schema=False)
    def live():
        return {"status": "up"}

    @app.get("/health/ready")
    @app.get("/api/health/ready", include_in_schema=False)
    def ready():
        if factory is None:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        try:
            with factory() as session:
                session.execute(text("SELECT 1"))
                session.execute(text("SELECT id FROM workspace_meta LIMIT 1"))
                if settings.require_migrations:
                    revisions = set(session.scalars(text("SELECT version_num FROM alembic_version")))
                    if revisions != {EXPECTED_SCHEMA_REVISION}:
                        return JSONResponse({"status": "not_ready", "reason": "migrations_required"}, status_code=503)
            return {"status": "ready"}
        except SQLAlchemyError:
            return JSONResponse({"status": "not_ready", "reason": "database_or_schema_unavailable"}, status_code=503)

    @app.get("/api/me")
    def me(actor: Actor = Depends(actor_for_request)):
        return actor.as_dict()

    @app.get("/api/workspace")
    def workspace(actor: Actor = Depends(actor_for_request), session: Session = Depends(session_dependency)):
        with session.begin():
            # The relational envelope needs a single coherent revision across
            # its multiple SELECTs under PostgreSQL's READ COMMITTED isolation.
            result = repository.get_workspace(session, lock=True)
        return JSONResponse(result, headers={"ETag": f'"{result["revision"]}"'})

    @app.put("/api/workspace")
    def put_workspace(body: WorkspaceWrite, actor: Actor = Depends(actor_for_request), session: Session = Depends(session_dependency)):
        require_editor(actor)
        with session.begin():
            current = repository.get_workspace(session, lock=True)
            if current["revision"] != body.revision:
                raise repository.RevisionConflict(current["revision"])
            normalized = validate_workspace(body.state)
            if requires_admin(current["state"], normalized, body.operation) and actor.role != "admin":
                raise HTTPException(403, detail={"code": "admin_required", "message": "An administrator is required for family ownership changes, deletion, import, reset or restore."})
            normalized = validate_transition(current["state"], normalized, operation=body.operation)
            result = repository.write_workspace(session, normalized, expected_revision=body.revision,
                actor=actor.as_dict(), reason=body.reason, operation=body.operation)
        return JSONResponse(result, headers={"ETag": f'"{result["revision"]}"'})

    @app.get("/api/availability")
    def availability(as_of: str | None = None, actor: Actor = Depends(actor_for_request), session: Session = Depends(session_dependency)):
        as_of = as_of or today_pacific()
        if not valid_date(as_of):
            raise HTTPException(422, detail={"code": "invalid_date", "message": "as_of must be a valid YYYY-MM-DD date."})
        with session.begin():
            current = repository.get_workspace(session, lock=True)
        return {"revision": current["revision"], "asOf": as_of, **allocation_plan(current["state"], as_of)}

    if settings.enable_api_docs:
        @app.get("/api/openapi.json", include_in_schema=False)
        def openapi_document(actor: Actor = Depends(actor_for_request)):
            return app.openapi()

        @app.get("/api/docs", include_in_schema=False, response_class=HTMLResponse)
        def docs(actor: Actor = Depends(actor_for_request)):
            return "<!doctype html><html><head><title>ASIC Tracker API</title></head><body><h1>ASIC Tracker API</h1><p><a href='/api/openapi.json'>Download the OpenAPI specification</a></p><p>GET /api/me, GET/PUT /api/workspace, GET /api/availability?as_of=YYYY-MM-DD.</p><p>All planning endpoints require the configured identity and role. PUT uses a revision-checked atomic transaction.</p></body></html>"

    if settings.frontend_dir and Path(settings.frontend_dir).is_dir():
        # Registered last so /api and health routes can never be shadowed.
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app


app = create_app()
