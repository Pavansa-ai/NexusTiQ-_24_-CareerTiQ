"""
Banking Transaction Risk Investigation Assistant
================================================
Single entry point — python app.py

Starts FastAPI + Uvicorn on port 8000.
Serves the frontend (frontend/dist/index.html) as a static HTML app.
Loads/builds the local RAG embedding index on startup.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router, set_embedding_index
from src.ai.embeddings import load_or_build_index

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="Banking Transaction Risk Investigation Assistant",
        description="Deterministic + Gemini AI hybrid transaction risk investigation system.",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes (mounted first so they take priority)
    app.include_router(router, prefix="/api")

    # Serve built frontend from frontend/dist/
    frontend_dist = Path("frontend/dist")
    index_file = frontend_dist / "index.html"

    if index_file.exists():
        # Serve any static assets directory if it exists
        assets_path = frontend_dist / "assets"
        if assets_path.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")

        @app.get("/", include_in_schema=False)
        async def serve_root():
            return FileResponse(str(index_file))

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            # For unknown paths that aren't API calls, return index.html (SPA routing)
            if full_path.startswith("api/"):
                return JSONResponse({"error": "Not found"}, status_code=404)
            return FileResponse(str(index_file))
    else:
        @app.get("/", include_in_schema=False)
        async def no_frontend():
            return JSONResponse({
                "message": "Banking Transaction Risk Investigation Assistant API",
                "note": "Frontend build not found at frontend/dist/index.html",
                "api_docs": "/docs",
                "health": "/api/health",
            })

    return app


# ---------------------------------------------------------------------------
# Startup tasks
# ---------------------------------------------------------------------------

def startup() -> None:
    logger.info("=" * 60)
    logger.info("Banking Transaction Risk Investigation Assistant")
    logger.info("SIH 2024 · Track ID: PS6")
    logger.info("=" * 60)

    # Check for GEMINI_API_KEY
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "⚠️  GEMINI_API_KEY not set in environment. "
            "AI explanations will be unavailable. "
            "Set it with: set GEMINI_API_KEY=your_key_here (Windows) "
            "or export GEMINI_API_KEY=your_key_here (Linux/Mac). "
            "Deterministic analysis will still work fully."
        )
    else:
        key_preview = api_key[:8] + "..." + api_key[-4:]
        logger.info(f"✓ GEMINI_API_KEY detected ({key_preview})")

    # Load / build embedding index
    logger.info("Loading local RAG embedding index from data/documents/…")
    try:
        index = load_or_build_index()
        set_embedding_index(index)
        chunk_count = len(index.chunks)
        has_embeddings = index.matrix is not None
        logger.info(
            f"✓ Embedding index ready: {chunk_count} chunks, "
            f"embeddings={'Gemini vectors' if has_embeddings else 'keyword fallback (no API key)'}"
        )
    except Exception as exc:
        logger.error(f"Failed to load embedding index: {exc}. RAG will be unavailable.")
        set_embedding_index(None)

    # Check frontend
    frontend_dist = Path("frontend/dist/index.html")
    if frontend_dist.exists():
        logger.info("✓ Frontend found at frontend/dist/index.html")
    else:
        logger.warning("⚠️  Frontend not found. API-only mode.")

    logger.info("=" * 60)
    logger.info("✓ Application ready at http://localhost:8000")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    startup()
    app = create_app()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True,
    )
