"""
Phase 2 — Event Ingestion API
POST /v1/pixel/event
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, status
from pydantic import BaseModel, UUID4, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..models.events import PixelEventRaw, PixelEventQueue

router = APIRouter(prefix="/v1/pixel", tags=["pixel"])


# ─── Pydantic Schema ──────────────────────────────────────────────────────────

class EventPayload(BaseModel):
    event_id: UUID4
    event_name: str = Field(..., max_length=100)

    visitor_id: str = Field(..., max_length=100)
    session_id: str = Field(..., max_length=100)

    url: Optional[str] = None
    path: Optional[str] = None
    referrer: Optional[str] = None

    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None

    fbclid: Optional[str] = None
    gclid: Optional[str] = None
    ttclid: Optional[str] = None
    msclkid: Optional[str] = None

    user_agent: Optional[str] = None

    # Unix timestamp sent by the pixel
    timestamp: Optional[int] = None

    # Optional enrichment fields (purchase, product_view, etc.)
    order_id: Optional[str] = None
    order_value: Optional[float] = None
    currency: Optional[str] = None
    email_hash: Optional[str] = None
    product_id: Optional[str] = None
    variant_id: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[int] = None
    cart_value: Optional[float] = None
    item_count: Optional[int] = None


# ─── Endpoint ─────────────────────────────────────────────────────────────────

ALLOWED_EVENTS = {
    "page_view",
    "product_view",
    "add_to_cart",
    "checkout_start",
    "purchase",
}


@router.post("/event", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    payload: EventPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Validate event name
    if payload.event_name not in ALLOWED_EVENTS:
        # Accept unknown events but flag them — don't reject to avoid data loss
        pass

    # Resolve event timestamp
    if payload.timestamp:
        event_ts = datetime.fromtimestamp(payload.timestamp, tz=timezone.utc)
    else:
        event_ts = datetime.now(timezone.utc)

    # Extract real IP (handle proxies)
    ip = _extract_ip(request)

    # ── Write raw event (immutable) ──────────────────────────────────────────
    raw_event = PixelEventRaw(
        event_id=payload.event_id,
        visitor_id=payload.visitor_id,
        session_id=payload.session_id,
        event_name=payload.event_name,
        url=payload.url,
        path=payload.path,
        referrer=payload.referrer,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        utm_content=payload.utm_content,
        utm_term=payload.utm_term,
        fbclid=payload.fbclid,
        gclid=payload.gclid,
        ttclid=payload.ttclid,
        msclkid=payload.msclkid,
        user_agent=payload.user_agent or request.headers.get("user-agent"),
        ip_address=ip,
        event_timestamp=event_ts,
    )
    db.add(raw_event)

    # ── Enqueue for async processing ─────────────────────────────────────────
    queue_entry = PixelEventQueue(
        id=uuid.uuid4(),
        event_id=payload.event_id,
        status="pending",
    )
    db.add(queue_entry)

    await db.commit()

    return {"status": "accepted", "event_id": str(payload.event_id)}


# ─── Health check ─────────────────────────────────────────────────────────────

@router.get("/health")
async def pixel_health(db: AsyncSession = Depends(get_db)):
    """Quick liveness check for the pixel endpoint."""
    return {"status": "ok"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
