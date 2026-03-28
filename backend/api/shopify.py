"""
Phase 6 — Shopify Webhook Handler

Receives orders/created webhook from Shopify.
Stores order, hashes customer email, and triggers identity stitching.

Webhook URL per client:  POST /v1/shopify/{client_id}/webhook/orders/created
Configure each Shopify store to point at its own client-specific URL.
"""

import hashlib
import hmac
import base64
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..models.clients import Client
from ..models.orders import Order
from ..services.identity_graph import stitch_identity, hash_email

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/shopify", tags=["shopify"])


# ─── Webhook Verification ─────────────────────────────────────────────────────

async def _verify_shopify_hmac(request: Request, secret: str):
    """Verify Shopify HMAC-SHA256 signature using the client's webhook secret."""
    if not secret:
        log.warning("Client has no shopify_webhook_secret — skipping HMAC verification")
        return

    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
    body = await request.body()

    digest = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    computed = base64.b64encode(digest).decode()

    if not hmac.compare_digest(computed, hmac_header):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid HMAC")


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/{client_id}/webhook/orders/created", status_code=status.HTTP_200_OK)
async def orders_created(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Resolve client
    result = await db.execute(select(Client).where(Client.client_id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Unknown client_id")

    await _verify_shopify_hmac(request, client.shopify_webhook_secret or "")

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
        client_id=client_id,
        customer_email_hash=email_hash,
        order_value=order_value,
        currency=currency,
        line_items=data.get("line_items"),
        shopify_created_at=shopify_created_at,
    )
    db.add(order)

    # Identity stitching happens via the pixel purchase event (which carries the
    # real browser visitor_id + email_hash). The webhook alone doesn't know the
    # visitor_id, so we don't create an identity graph record here.

    await db.commit()

    log.info("Order %s ingested for client %s, email_hash=%s", order_id, client_id, email_hash)
    return {"status": "ok", "order_id": order_id}
