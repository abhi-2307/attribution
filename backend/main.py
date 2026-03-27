"""
Attribution Platform — FastAPI Application
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
import logging
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .db.database import engine, get_db
from .models import Base, Client, PixelEventRaw, PixelEventQueue, Session, Order, OrderJourney, IdentityGraph  # noqa: F401 — registers all models

from .api.pixel import router as pixel_router
from .api.shopify import router as shopify_router
from .api.attribution import router as attribution_router
from .workers import session_builder, journey_builder, attribution_worker

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
async def startup():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS attribution"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema and tables ensured.")

    # Start background workers
    asyncio.create_task(session_builder.run())
    asyncio.create_task(journey_builder.run())
    asyncio.create_task(attribution_worker.run())
    logger.info("Background workers started.")

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
    js = js.replace("{{CLIENT_ID}}", "")
    return Response(content=js, media_type="application/javascript")


@app.get("/pixel/{client_id}/pixel.js", include_in_schema=False)
async def serve_pixel_js_for_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Serve pixel.js pre-configured for a specific client. Embed as:
    <script src="https://your-api.com/pixel/YOUR_CLIENT_ID/pixel.js"></script>
    """
    result = await db.execute(select(Client).where(Client.client_id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Unknown client_id")

    logger.info("Serving pixel.js for client=%s", client_id)
    js = _PIXEL_JS_PATH.read_text()
    js = js.replace("{{PIXEL_BASE_URL}}", PIXEL_BASE_URL)
    js = js.replace("{{CLIENT_ID}}", client_id)
    return Response(content=js, media_type="application/javascript")


@app.get("/")
async def root():
    return {"service": "attribution-platform", "version": "0.1.0"}
