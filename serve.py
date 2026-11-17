"""Expose the existing FastAPI routes and the compiled Vite site on one origin.
Do NOT add test authentication bypasses, public admin endpoints, or QA controls.
"""
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from app.main import app

assets = Path(__file__).resolve().parent / "frontend_dist"
if not (assets / "index.html").is_file():
    raise RuntimeError("Missing React production build")

# Mount last: registered /api/v1, /health and /docs handlers retain precedence.
app.mount("/", StaticFiles(directory=str(assets), html=True), name="frontend")
