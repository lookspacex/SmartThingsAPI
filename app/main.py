from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import engine
from app.envelope import EnvelopeMiddleware
from app.http_errors import UpstreamHTTPError
from app.models import Base
from app.routes.aircon import router as aircon_router
from app.routes.auth import router as auth_router
from app.routes.devices import router as devices_router
from app.routes.smartapp import router as smartapp_router
from app.routes.smartthings_oauth import router as smartthings_oauth_router
from app.routes.tv import router as tv_router
from app.routes.users import router as users_router


def create_app() -> FastAPI:
    docs_url = "/docs" if settings.app_env != "prod" else None
    redoc_url = "/redoc" if settings.app_env != "prod" else None
    openapi_url = "/openapi.json" if settings.app_env != "prod" else None
    app = FastAPI(title=settings.app_name, docs_url=docs_url, redoc_url=redoc_url, openapi_url=openapi_url)

    # CORS
    origins_raw = (settings.cors_allow_origins or "").strip()
    if origins_raw == "*" or origins_raw == "":
        origins = ["*"]
    else:
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(EnvelopeMiddleware)

    @app.on_event("startup")
    def _startup() -> None:
        # Minimal bootstrap: create tables if they do not exist.
        # For production, you typically want migrations instead of create_all.
        Base.metadata.create_all(bind=engine)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(UpstreamHTTPError)
    async def upstream_http_error_handler(request: Request, exc: UpstreamHTTPError) -> JSONResponse:
        return JSONResponse(
            status_code=int(exc.status_code) if exc.status_code else 502,
            content={
                "code": int(exc.status_code) if exc.status_code else 502,
                "msg": exc.message,
                "data": exc.details,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            # Preferred: caller already provided envelope-style detail
            if "code" in detail and "msg" in detail and "data" in detail:
                body = {"code": int(detail["code"]), "msg": str(detail["msg"]), "data": detail.get("data")}
            else:
                # Back-compat: old shape {"code": "...", "message": "...", "details": ...}
                body = {
                    "code": int(detail.get("code", exc.status_code)),
                    "msg": str(detail.get("msg") or detail.get("message") or "Request failed"),
                    "data": detail.get("data") if "data" in detail else detail.get("details"),
                }
        else:
            body = {"code": int(exc.status_code), "msg": str(detail), "data": None}
        return JSONResponse(
            status_code=exc.status_code,
            content=body,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": 422,
                "msg": "Request validation failed",
                "data": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Keep errors consistent for clients. In prod, avoid leaking internals.
        data = {"error": str(exc)} if settings.app_env != "prod" else None
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "msg": "Internal Server Error",
                "data": data,
            },
        )

    app.include_router(devices_router)
    app.include_router(auth_router)
    app.include_router(aircon_router)
    app.include_router(tv_router)
    app.include_router(users_router)
    app.include_router(smartthings_oauth_router)
    app.include_router(smartapp_router)
    return app


app = create_app()