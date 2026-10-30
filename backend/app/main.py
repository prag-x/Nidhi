import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from . import __version__
from .api import (
    admin,
    alerts,
    ask,
    auth,
    dashboard,
    institutions,
    instruments,
    intelligence,
    meta,
    public,
    reports,
    stream,
)
from .config import get_settings
from .db import SessionLocal, engine
from .services.events import broker
from .services.sweeps import run_sweep

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("nidhi")
SWEEP_LOCK_ID = 7212026


def run_sweep_once() -> dict | None:
    """Run the periodic checks; with Postgres an advisory lock keeps it to one worker at a time."""
    with engine.connect() as conn:
        pg = conn.dialect.name == "postgresql"
        if pg and not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SWEEP_LOCK_ID}).scalar():
            return None
        try:
            with Session(bind=conn) as db:
                return run_sweep(db)
        finally:
            if pg:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SWEEP_LOCK_ID})
                conn.commit()


async def scheduler(interval: int) -> None:
    await asyncio.sleep(3)
    while True:
        try:
            stats = await asyncio.to_thread(run_sweep_once)
            if stats and any(stats.values()):
                log.info("sweep: %s", stats)
        except Exception:
            log.exception("periodic sweep failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    broker.bind_loop(asyncio.get_running_loop())
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    task = None
    if settings.scheduler_enabled:
        task = asyncio.create_task(scheduler(settings.scheduler_interval_seconds))
    log.info("Nidhi %s started (%s, db=%s)", __version__, settings.environment, engine.dialect.name)
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="Nidhi API",
    description="AICTE Security Deposit / FDR Management Portal.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/api") and request.url.path != "/api/stream":
        response.headers.setdefault("Cache-Control", "no-store")
        if elapsed > 1000:
            log.warning("slow request %s %s %.0fms", request.method, request.url.path, elapsed)
    return response


@app.exception_handler(OverflowError)
async def out_of_range(request: Request, exc: OverflowError):
    # An id or number too large for the database column (e.g. /instruments/99999999999999999999) cannot exist.
    return JSONResponse({"detail": "Not found."}, status_code=404)


@app.exception_handler(DataError)
async def bad_value(request: Request, exc: DataError):
    # PostgreSQL rejects out-of-range numbers and malformed values at the driver level.
    log.info("rejected value on %s %s: %s", request.method, request.url.path, exc.orig)
    return JSONResponse({"detail": "A value in the request is out of range or malformed."}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong on the server. The error has been logged."}, status_code=500)


for module in (auth, meta, dashboard, instruments, institutions, alerts, reports, admin, public, stream, intelligence, ask):
    app.include_router(module.router, prefix="/api")
app.include_router(instruments.files_router, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    finally:
        db.close()
    return {"status": "ok" if db_ok else "degraded", "database": engine.dialect.name, "db_ok": db_ok,
            "version": __version__, "demo_mode": settings.demo_mode, "timezone": settings.timezone}


if settings.static_dir and Path(settings.static_dir, "index.html").is_file():
    # Single-container deployment: serve the built web app and fall back to index.html for client-side routes.
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _static = Path(settings.static_dir).resolve()
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)
        candidate = (_static / path).resolve()
        if path and candidate.is_file() and _static in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(_static / "index.html", headers={"Cache-Control": "no-cache"})
