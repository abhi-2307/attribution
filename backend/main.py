"""
Attribution Platform — FastAPI Application
"""

from dotenv import load_dotenv
load_dotenv()

import os
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from sqlalchemy import text
from .db.database import engine
from .models import Base, PixelEventRaw, PixelEventQueue, Session, Order, OrderJourney, IdentityGraph  # noqa: F401 — registers all models

from .api.pixel import router as pixel_router
from .api.shopify import router as shopify_router
from .api.attribution import router as attribution_router

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PIXEL_BASE_URL = os.environ.get("PIXEL_BASE_URL", "http://localhost:8000")
_PIXEL_JS_PATH = Path(__file__).parent.parent / "pixel" / "pixel.js"

logger.info("=== Attribution Platform Starting ===")
logger.info("PIXEL_BASE_URL = %s", PIXEL_BASE_URL)
logger.info("pixel.js path  = %s (exists=%s)", _PIXEL_JS_PATH, _PIXEL_JS_PATH.exists())
logger.info("DATABASE_URL set = %s", bool(os.environ.get("DATABASE_URL")))

app = FastAPI(
    title="Attribution Platform",
    description="First-party attribution system — pixel ingestion, session building, journey reconstruction, and attribution engine.",
    version="0.1.0",
)


@app.on_event("startup")
async def create_tables():
    async with engine.begin() as conn:
        # Create the attribution schema if it doesn't exist
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS attribution"))
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema and tables ensured.")

# Pixel must accept requests from any domain.
# allow_credentials=True requires explicit origins (not "*"), so we use allow_origin_regex instead.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(pixel_router)
app.include_router(shopify_router)
app.include_router(attribution_router)


@app.get("/pixel.js", include_in_schema=False)
async def serve_pixel_js():
    logger.info("Serving pixel.js — PIXEL_BASE_URL=%s", PIXEL_BASE_URL)
    js = _PIXEL_JS_PATH.read_text()
    js = js.replace("{{PIXEL_BASE_URL}}", PIXEL_BASE_URL)
    return Response(content=js, media_type="application/javascript")


@app.get("/")
async def root():
    return {"service": "attribution-platform", "version": "0.1.0"}
