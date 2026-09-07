import os
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.database import engine, Base
from app.seed import seed_database
from app.routes.public import router as public_router
from app.routes.admin import router as admin_router
from app.routes.api import router as api_router

_initialized = False

def init_app_state():
    global _initialized
    if _initialized:
        return
    try:
        # Create tables if not existing
        Base.metadata.create_all(bind=engine)
        from app.database_migration import run_migrations
        run_migrations()
        if not settings.IS_VERCEL:
            seed_database()
        _initialized = True
    except Exception as e:
        print(f"App state init notice: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_app_state()
    # Start autonomous background scheduler task
    import asyncio
    from app.services.auto_scheduler import AutoSchedulerService
    scheduler_task = asyncio.create_task(AutoSchedulerService.start_background_loop())
    try:
        yield
    finally:
        AutoSchedulerService.stop_background_loop()
        scheduler_task.cancel()

app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise AI-Powered Content Automation and Publishing Platform",
    version="2.0.0",
    lifespan=lifespan,
    redirect_slashes=False
)

from starlette.types import ASGIApp, Scope, Receive, Send
import urllib.parse

class VercelPathMiddleware:
    def __init__(self, inner: ASGIApp):
        self.inner = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            query_bytes = scope.get("query_string", b"")
            if b"__vercel_path=" in query_bytes:
                params = urllib.parse.parse_qs(query_bytes.decode("latin1", errors="replace"), keep_blank_values=True)
                if "__vercel_path" in params:
                    dest = params.pop("__vercel_path")[0]
                    if not dest.startswith("/"):
                        dest = "/" + dest
                    scope["path"] = dest
                    scope["raw_path"] = dest.encode("ascii")
                    scope["query_string"] = urllib.parse.urlencode(params, doseq=True).encode("latin1")
            elif path.startswith("/api/index.py"):
                sub = path[len("/api/index.py"):]
                dest = sub if sub.startswith("/") else "/" + sub
                scope["path"] = dest
                scope["raw_path"] = dest.encode("ascii")
            elif path.startswith("/api/index"):
                sub = path[len("/api/index"):]
                dest = sub if sub.startswith("/") else "/" + sub
                scope["path"] = dest
                scope["raw_path"] = dest.encode("ascii")
            elif path == "/api":
                scope["path"] = "/"
                scope["raw_path"] = b"/"

        await self.inner(scope, receive, send)

app.add_middleware(VercelPathMiddleware)

from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Dedicated, resilient route to serve all uploaded images across local and Vercel environments
@app.get("/static/uploads/{filename}")
@app.get("/media/{filename}")
async def get_uploaded_image(filename: str):
    clean_filename = Path(filename).name
    candidates = [
        Path("/tmp/uploads") / clean_filename,
        Path(__file__).resolve().parent / "static" / "uploads" / clean_filename,
        settings.BASE_DIR / "static" / "uploads" / clean_filename,
        settings.BASE_DIR / "app" / "static" / "uploads" / clean_filename,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            media_type = "image/png" if clean_filename.endswith(".png") else "image/svg+xml"
            if clean_filename.endswith(".jpg") or clean_filename.endswith(".jpeg"):
                media_type = "image/jpeg"
            elif clean_filename.endswith(".webp"):
                media_type = "image/webp"
            return FileResponse(path=str(c), media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})

    # Dynamic fallback SVG card ensures images NEVER break or 404
    from app.services.image_service import ImageService
    svg_code = ImageService.render_fallback_svg(clean_filename)
    return Response(content=svg_code, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

# Safe mounting of static directory (CSS, JS, fonts)
if settings.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

# Templates for error pages
templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

# Health check route
@app.get("/health")
def health():
    return {"status": "ok", "platform": "TrendBlogo", "environment": settings.APP_ENV}

# Route to serve IndexNow verification key file for search engines
@app.get("/{filename}.txt")
def get_txt_verification(filename: str):
    if filename == "robots":
        from app.services.seo_engine import SEOEngine
        return Response(content=SEOEngine.generate_robots_txt(), media_type="text/plain")
    from app.services.indexing_service import IndexingService
    key = IndexingService.get_indexnow_key()
    if filename == key or filename == "indexnow":
        return Response(content=key, media_type="text/plain")
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="File not found")

# Register Routers
app.include_router(public_router)
app.include_router(admin_router)
app.include_router(api_router)

# Custom 404 and 500 error handlers
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    path_str = str(request.url.path)
    if "/static/uploads/" in path_str:
        from app.services.image_service import ImageService
        filename = path_str.split("/")[-1]
        svg_code = ImageService.render_fallback_svg(filename)
        return Response(content=svg_code, media_type="image/svg+xml", status_code=200)

    headers = {
        "X-Debug-Req-Path": str(request.url.path),
        "X-Debug-Scope-Path": str(request.scope.get("path")),
        "X-Debug-Matched-Path": str(request.headers.get("x-matched-path")),
        "X-Debug-All-Headers": str(list(request.headers.keys()))
    }
    return templates.TemplateResponse(
        request=request,
        name="404.html",
        context={
            "request": request,
            "title": "Page Not Found (404) ? TrendBlogo",
            "meta_desc": "The page you are looking for does not exist or has been moved.",
            "base_url": settings.BASE_URL
        },
        status_code=404,
        headers=headers
    )

@app.exception_handler(500)
async def custom_500_handler(request: Request, exc):
    return HTMLResponse(
        """<!DOCTYPE html>
<html lang="en">
<head><title>System Error ? TrendBlogo</title><meta charset="utf-8"></head>
<body style="font-family:system-ui;text-align:center;padding:80px;background:#0F172A;color:#F8FAFC;">
  <h1 style="font-size:32px;color:#F43F5E;">An unexpected error occurred</h1>
  <p style="color:#94A3B8;max-width:500px;margin:20px auto;">The TrendBlogo platform encountered an internal error. Please check system logs in the administrator console.</p>
  <a href="/" style="display:inline-block;padding:12px 24px;background:#4F46E5;color:white;border-radius:8px;text-decoration:none;font-weight:600;">Return Home</a>
</body>
</html>""",
        status_code=500
    )
