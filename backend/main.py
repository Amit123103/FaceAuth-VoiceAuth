"""
FaceAuth — Main Application Entry Point
=========================================
FastAPI application with CORS, static files, lifespan events,
and all route modules.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Triggering reload to apply DB migrations...
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime

from backend.config import get_settings, BASE_DIR
from backend.database.database import init_db, close_db
from backend.middleware.security import SecurityHeadersMiddleware, RequestLoggingMiddleware

# Configure logging
LOG_FILE = BASE_DIR / "faceauth.log"
log_format = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ],
)
# Added comment to trigger reload: Verifying Biometric Fusion Stability 2026-03-30
logger = logging.getLogger("faceauth")
logger.info(f"LOGGING TO: {LOG_FILE}")

settings = get_settings()

# Paths
FRONTEND_DIR = BASE_DIR / "frontend"


# ── Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # — Startup —
    logger.info("============================================================")
    logger.info(f"  [START] {settings.app_name} starting...")
    logger.info(f"  [ENV]   Environment: {settings.app_env}")
    logger.info("============================================================")

    # Initialize database
    await init_db()
    logger.info("[DB] Database initialized")

    # Schedule backups
    if settings.backup_enabled:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from backend.database.backup import scheduled_backup

            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                scheduled_backup,
                "interval",
                hours=settings.backup_interval_hours,
                id="auto_backup",
                name="Automatic Database Backup",
            )
            scheduler.start()
            logger.info(f"[JOB] Backup scheduler started (every {settings.backup_interval_hours}h)")
        except ImportError:
            logger.warning("[WARN] APScheduler not installed — automatic backups disabled")

    logger.info(f"[READY] Server ready at http://{settings.app_host}:{settings.app_port}")

    yield

    # — Shutdown —
    logger.info("[SHUTDOWN] Shutting down...")
    await close_db()
    logger.info("[SHUTDOWN] Database connections closed")


# ── App ──────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    description="Enterprise-grade Face Recognition Authentication System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.app_debug else None,
    redoc_url="/api/redoc" if settings.app_debug else None,
)


# ── Middleware ───────────────────────────────────────────────

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Note: Temporarily removed custom middlewares to isolate the 500 error cause.
# app.add_middleware(SecurityHeadersMiddleware)
# app.add_middleware(RequestLoggingMiddleware)


# ── Routes ───────────────────────────────────────────────────

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve a professional biometric favicon as SVG."""
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" rx="20" fill="#0A0B0E"/>
        <circle cx="50" cy="45" r="25" fill="none" stroke="#00D2FF" stroke-width="4" stroke-dasharray="10 5"/>
        <path d="M30 80 Q50 65 70 80" fill="none" stroke="#00D2FF" stroke-width="4" stroke-linecap="round"/>
        <circle cx="50" cy="45" r="5" fill="#00D2FF"/>
    </svg>
    """
    return Response(content=svg, media_type="image/svg+xml")

from backend.routes.auth_routes import router as auth_router
from backend.routes.user_routes import router as user_router
from backend.routes.face_routes import router as face_router
from backend.routes.admin_routes import router as admin_router
from backend.routes.voice_routes import router as voice_router

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(face_router)
app.include_router(admin_router)
app.include_router(voice_router)


# ── Health Check ─────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": "1.0.0",
    }


# ── Static Files ─────────────────────────────────────────────

# Serve frontend static assets
if FRONTEND_DIR.exists():
    app.mount(
        "/css",
        StaticFiles(directory=str(FRONTEND_DIR / "css")),
        name="css",
    )
    app.mount(
        "/js",
        StaticFiles(directory=str(FRONTEND_DIR / "js")),
        name="js",
    )
    if (FRONTEND_DIR / "assets").exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(FRONTEND_DIR / "assets")),
            name="assets",
        )
    # Emergency asset serving for generated hero image
    @app.get("/assets/hero-biometric.webp")
    async def serve_hero_image():
        hero_path = Path(r"C:\Users\amita\.gemini\antigravity\brain\66f2842a-c00c-40c3-8e8f-72353c990428\hero_biometric_1774891107981.png")
        if hero_path.exists():
             return FileResponse(hero_path)
        return JSONResponse({"error": "Hero image not found"}, status_code=404)


# ── Frontend Page Routes ─────────────────────────────────────

@app.get("/")
@app.get("/index.html")
async def serve_index():
    """Serve the landing page."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/login")
async def serve_login():
    """Serve the biometric login hub."""
    return FileResponse(str(FRONTEND_DIR / "login.html"))


@app.get("/register")
async def serve_register():
    """Serve the registration page."""
    return FileResponse(str(FRONTEND_DIR / "register.html"))


@app.get("/dashboard")
async def serve_dashboard():
    """Serve the user dashboard."""
    return FileResponse(str(FRONTEND_DIR / "dashboard.html"))


@app.get("/admin")
async def serve_admin():
    """Serve the admin panel."""
    return FileResponse(str(FRONTEND_DIR / "admin.html"))


# ── Global Error Handler ─────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler for unhandled exceptions."""
    error_msg = f"CRASH: {type(exc).__name__}: {str(exc)}"
    logger.error(error_msg, exc_info=True)
    
    # Emergency write to file
    try:
        with open("crash_debug.txt", "a") as f:
            f.write(f"{datetime.now()} | {error_msg}\n")
    except:
        pass

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "error": str(exc),
            "type": type(exc).__name__,
        },
    )


# ── Run with Uvicorn ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_level="info",
    )
