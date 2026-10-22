"""FastAPI application entry point: ``uvicorn backend.main:app``."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api import applications, auth, billing, companies, inbox, jobs, profile, settings as settings_api
from backend.config import ROOT_DIR, get_settings
from backend.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("aijh")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    init_db()
    if settings.run_scheduler:
        from backend.jobs.scheduler import start_scheduler, stop_scheduler
        start_scheduler()
        yield
        stop_scheduler()
    else:
        yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan,
                  docs_url=None if settings.is_production else "/api/docs", redoc_url=None,
                  openapi_url=None if settings.is_production else "/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Something went wrong. Check the server log."}, status_code=500)

    for module in (auth, profile, jobs, companies, applications, inbox, billing, settings_api):
        app.include_router(module.router)

    @app.get("/ads.txt", include_in_schema=False)
    @app.get("/app-ads.txt", include_in_schema=False)
    def ads_txt():
        """Authorises Google to sell ads for this site/app (AdSense ads.txt, AdMob app-ads.txt)."""
        from fastapi.responses import PlainTextResponse

        import os

        ids = {i.strip().replace("ca-app-pub-", "pub-").replace("ca-pub-", "pub-").split("~")[0]
               for i in (settings.adsense_client, os.getenv("ADMOB_PUBLISHER_ID", "")) if i.strip()}
        ids = sorted(i for i in ids if i.startswith("pub-"))
        if not settings.ads_enabled or not ids:
            return PlainTextResponse("", status_code=404)
        return PlainTextResponse("".join(f"google.com, {i}, DIRECT, f08c47fec0942fa0\n" for i in ids))

    @app.get("/api/health")
    def health():
        return {"status": "ok", "env": settings.env}

    # Serve the built frontend (single-container deployments).
    dist = Path(ROOT_DIR / "frontend" / "dist")
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found."}, status_code=404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
                headers = {"Cache-Control": "no-cache"} if path in ("sw.js", "manifest.webmanifest") else None
                return FileResponse(candidate, headers=headers)
            return FileResponse(dist / "index.html")
    return app


app = create_app()
