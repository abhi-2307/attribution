"""
Attribution Platform — FastAPI Application
"""

from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .api.pixel import router as pixel_router
from .api.shopify import router as shopify_router
from .api.attribution import router as attribution_router

PIXEL_BASE_URL = os.environ.get("PIXEL_BASE_URL", "http://localhost:8000")
_PIXEL_JS_PATH = Path(__file__).parent.parent / "pixel" / "pixel.js"

app = FastAPI(
    title="Attribution Platform",
    description="First-party attribution system — pixel ingestion, session building, journey reconstruction, and attribution engine.",
    version="0.1.0",
)

# Allow the pixel script to POST from any domain (restrict origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(pixel_router)
app.include_router(shopify_router)
app.include_router(attribution_router)


@app.get("/pixel.js", include_in_schema=False)
async def serve_pixel_js():
    js = _PIXEL_JS_PATH.read_text()
    js = js.replace("{{PIXEL_BASE_URL}}", PIXEL_BASE_URL)
    return Response(content=js, media_type="application/javascript")


@app.get("/")
async def root():
    return {"service": "attribution-platform", "version": "0.1.0"}
