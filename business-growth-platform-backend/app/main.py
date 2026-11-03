import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

from app.config import get_settings
from app.database import db, one
from app.meta import MetaAPIError
from app.routes import automations, content, engagement, instagram, workspaces
from app.worker import worker_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    config = get_settings()
    task = asyncio.create_task(worker_loop(config)) if config.scheduler_enabled else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="Growthboard API", version="0.3.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(settings.frontend_url).rstrip("/")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(workspaces.router)
app.include_router(instagram.router)
app.include_router(content.router)
app.include_router(engagement.router)
app.include_router(automations.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(MetaAPIError)
async def instagram_error(_request, _error):
    return JSONResponse(
        status_code=502,
        content={
            "detail": "Instagram could not complete this action. Check the granted permissions, account connection and message window."
        },
    )


@app.exception_handler(httpx.HTTPError)
async def network_error(_request, _error):
    return JSONResponse(
        status_code=502,
        content={
            "detail": "The upstream service did not respond. Check the activity result before retrying a public action."
        },
    )


@app.exception_handler(APIError)
async def database_error(_request, _error):
    return JSONResponse(
        status_code=503,
        content={
            "detail": "This feature is unavailable in the database. Check the applied Growthboard migrations."
        },
    )


@app.get("/health/ready")
def readiness():
    try:
        db().table("automation_rules").select("id").limit(0).execute()
        scheduler = one(
            db()
            .table("scheduler_configuration")
            .select("last_finished_at,last_result")
            .eq("name", "mvp")
            .execute()
        )
        return {
            "status": "ready" if scheduler else "migration_required",
            "version": app.version,
            "scheduler": scheduler or {},
            "background_worker_enabled": settings.scheduler_enabled,
        }
    except Exception:  # noqa: BLE001 - readiness reports a redacted dependency status
        return JSONResponse(
            status_code=503, content={"status": "not_ready", "version": app.version}
        )
