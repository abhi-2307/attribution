"""
Phase 6 — Shopify Webhook Handler

Receives orders/created webhook from Shopify.
Stores order, hashes customer email, and triggers identity stitching.
"""

import hashlib
import hmac
import base64
import os
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..models.orders import Order
from ..services.identity_graph import stitch_identity, hash_email

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/shopify", tags=["shopify"])

SHOPIFY_WEBHOOK_SECRET = os.environ.get("SHOPIFY_WEBHOOK_SECRET", "")


# ─── Webhook Verification ─────────────────────────────────────────────────────

async def _verify_shopify_hmac(request: Request):
    """Verify Shopify HMAC-SHA256 signature to ensure request authenticity."""
    if not SHOPIFY_WEBHOOK_SECRET:
        log.warning("SHOPIFY_WEBHOOK_SECRET not set — skipping HMAC verification")
        return

    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
    body = await request.body()

    log.info("X-Shopify-Hmac-Sha256 header: %s", hmac_header)
    log.info("SHOPIFY_WEBHOOK_SECRET (length only): %d", len(SHOPIFY_WEBHOOK_SECRET))

    digest = hmac.new(
        SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    computed = base64.b64encode(digest).decode()

    if not hmac.compare_digest(computed, hmac_header):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid HMAC")


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/webhook/orders/created", status_code=status.HTTP_200_OK)
async def orders_created(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await _verify_shopify_hmac(request)

    data = await request.json()

    order_id = str(data.get("id", ""))
    email = data.get("email") or data.get("contact_email") or ""
    order_value = float(data.get("total_price", 0))
    currency = data.get("currency", "USD")
    shopify_customer_id = str(data.get("customer", {}).get("id", "")) or None

    raw_created_at = data.get("created_at")
    shopify_created_at = (
        datetime.fromisoformat(raw_created_at.replace("Z", "+00:00"))
        if raw_created_at
        else datetime.now(timezone.utc)
    )

    email_hash = hash_email(email) if email else None

    # Store order (no raw PII)
    order = Order(
        order_id=order_id,
        customer_email_hash=email_hash,
        order_value=order_value,
        currency=currency,
        line_items=data.get("line_items"),
        shopify_created_at=shopify_created_at,
    )
    db.add(order)

    # Stitch identity
    if email:
        await stitch_identity(
            db,
            visitor_id=email_hash,  # temp visitor_id placeholder; resolved later
            email=email,
            shopify_customer_id=shopify_customer_id,
        )

    await db.commit()

    log.info("Order %s ingested, email_hash=%s", order_id, email_hash)
    return {"status": "ok", "order_id": order_id}
