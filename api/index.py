"""
Minimal Vercel diagnostic entry point.
This file tests if the Python runtime is working at all on Vercel.
Replace with the full app once confirmed working.
"""
import sys
import os
import traceback
from pathlib import Path

# ── 1. Ensure project root is on sys.path ────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ── 2. Mark as Vercel environment BEFORE any app import ──────────────────────
os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("VERCEL_ENV", "production")

# ── 3. Attempt to import the real FastAPI app ─────────────────────────────────
_boot_error: str = ""
_boot_traceback: str = ""

try:
    from app.main import app          # <-- the real application
    _boot_ok = True
except Exception as _exc:
    _boot_ok = False
    _boot_error = str(_exc)
    _boot_traceback = traceback.format_exc()

# ── 4. If the real app failed, expose a diagnostic ASGI app ──────────────────
if not _boot_ok:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, HTMLResponse

    app = FastAPI(title="TrendBlogo – Boot Diagnostic")

    @app.get("/health")
    async def _health():
        return JSONResponse(
            {"status": "boot_error", "error": _boot_error},
            status_code=500,
        )

    @app.api_route(
        "/{path_name:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    )
    async def _catch_all(request: Request, path_name: str = ""):
        accept = request.headers.get("accept", "")
        env_info = {k: v for k, v in os.environ.items() if k.startswith(("VERCEL", "PYTHON", "PATH"))}
        python_pkgs: str = ""
        try:
            import importlib.metadata as meta
            python_pkgs = ", ".join(
                f"{d.name}=={d.version}"
                for d in sorted(meta.distributions(), key=lambda x: x.name)
            )
        except Exception:
            python_pkgs = "Could not enumerate installed packages"

        if "text/html" in accept:
            return HTMLResponse(
                f"""<!DOCTYPE html>
<html>
<head>
  <title>TrendBlogo – Boot Error</title>
  <meta charset="utf-8">
  <style>
    body{{font-family:monospace;background:#0F172A;color:#F8FAFC;padding:30px;margin:0}}
    h2{{color:#F59E0B;margin-top:0}}
    pre{{background:#1E293B;padding:16px;border-radius:8px;color:#38BDF8;overflow:auto;white-space:pre-wrap;word-break:break-all;font-size:13px}}
    .label{{color:#94A3B8;margin-top:20px;font-weight:bold}}
  </style>
</head>
<body>
<h2>&#9888; TrendBlogo – Application Startup Failure</h2>
<div class="label">Error:</div>
<pre>{_boot_error}</pre>
<div class="label">Full Traceback:</div>
<pre>{_boot_traceback}</pre>
<div class="label">Python: {sys.version}</div>
<div class="label">Installed packages:</div>
<pre>{python_pkgs}</pre>
<div class="label">Vercel Env Vars:</div>
<pre>{env_info}</pre>
</body>
</html>""",
                status_code=500,
            )

        return JSONResponse(
            {
                "status": "boot_error",
                "error": _boot_error,
                "traceback": _boot_traceback,
                "python": sys.version,
                "env": env_info,
                "installed_packages": python_pkgs,
            },
            status_code=500,
        )
