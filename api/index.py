import sys
import os
import traceback
from pathlib import Path

# Add the project root to sys.path so that 'app' module can be found
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Explicitly set Vercel environment flag BEFORE any app imports
os.environ["VERCEL"] = "1"
os.environ["VERCEL_ENV"] = os.environ.get("VERCEL_ENV", "production")

_import_error = None
_error_detail = ""

try:
    from app.main import app

except Exception as e:
    _import_error = e
    _error_detail = traceback.format_exc()

    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="TrendBlogo – Boot Diagnostic")

    @app.get("/health")
    async def health_check():
        return JSONResponse({"status": "boot_error", "error": str(_import_error)}, status_code=500)

    @app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def catch_all_diag(request: Request, path_name: str = ""):
        # Return JSON for API calls, HTML for browser visits
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return HTMLResponse(
                f"""<!DOCTYPE html>
<html>
<head>
  <title>TrendBlogo – Startup Error</title>
  <meta charset="utf-8">
  <style>
    body {{ font-family: monospace; background: #0F172A; color: #F8FAFC; padding: 40px; }}
    h2 {{ color: #F59E0B; }}
    pre {{ background: #1E293B; padding: 20px; border-radius: 8px; color: #38BDF8; overflow: auto; white-space: pre-wrap; word-break: break-all; }}
    p {{ color: #94A3B8; }}
  </style>
</head>
<body>
  <h2>&#9888; TrendBlogo – Application Startup Failure</h2>
  <p>The application failed to start. Check environment variables and dependencies.</p>
  <pre>{_error_detail}</pre>
</body>
</html>""",
                status_code=500
            )
        return JSONResponse(
            {"status": "error", "message": "Application failed to start", "detail": str(_import_error)},
            status_code=500
        )
