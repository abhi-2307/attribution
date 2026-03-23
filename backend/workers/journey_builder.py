"""
Phase 7 — Journey Builder Worker

For each order, resolve the visitor_id via identity graph,
then look up sessions prior to purchase and build the touchpoint journey.

Run:
    python -m backend.workers.journey_builder
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import AsyncSessionLocal
from ..models.orders import Order, OrderJourney, IdentityGraph
from ..models.sessions import Session

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

POLL_INTERVAL_SECONDS = 15
BATCH_SIZE = 50


async def run():
    log.info("Journey builder started — polling every %ds", POLL_INTERVAL_SECONDS)
    while True:
        try:
            await process_batch()
        except Exception as e:
            log.error("Journey builder error: %s", e, exc_info=True)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def process_batch():
    async with AsyncSessionLocal() as db:
        # Find orders that don't yet have a journey
        result = await db.execute(
            select(Order)
            .outerjoin(OrderJourney, Order.order_id == OrderJourney.order_id)
            .where(OrderJourney.order_id.is_(None))
            .limit(BATCH_SIZE)
        )
        orders: list[Order] = list(result.scalars().all())

        if not orders:
            return

        log.info("Building journeys for %d orders", len(orders))

        for order in orders:
            await _build_journey(db, order)

        await db.commit()


async def _build_journey(db: AsyncSession, order: Order):
    if not order.customer_email_hash:
        log.warning("Order %s has no email_hash, skipping journey", order.order_id)
        return

    client_id = order.client_id

    # Resolve visitor_id via identity graph filtered by client_id
    result = await db.execute(
        select(IdentityGraph.visitor_id).where(
            IdentityGraph.client_id == client_id,
            IdentityGraph.email_hash == order.customer_email_hash,
        )
    )
    visitor_id = result.scalar_one_or_none()

    if not visitor_id:
        log.info("No visitor_id found for order %s (client %s)", order.order_id, client_id)
        return

    # Fetch all sessions for this visitor (same client) before the order date
    result = await db.execute(
        select(Session)
        .where(
            Session.client_id == client_id,
            Session.visitor_id == visitor_id,
            Session.session_start <= (order.shopify_created_at or datetime.now(timezone.utc)),
        )
        .order_by(Session.session_start.asc())
    )
    sessions: list[Session] = list(result.scalars().all())

    touchpoints = []
    for s in sessions:
        tp = {
            "session_id": s.session_id,
            "session_start": s.session_start.isoformat() if s.session_start else None,
            "session_end": s.session_end.isoformat() if s.session_end else None,
            "source": s.utm_source or _classify_source(s),
            "medium": s.utm_medium,
            "campaign": s.utm_campaign,
            "content": s.utm_content,
            "term": s.utm_term,
            "referrer": s.referrer,
            "landing_page": s.landing_page,
        }
        touchpoints.append(tp)

    journey = OrderJourney(
        order_id=order.order_id,
        client_id=client_id,
        visitor_id=visitor_id,
        touchpoints=touchpoints,
    )
    db.add(journey)
    log.info(
        "Journey built for order %s (client %s) — %d touchpoints",
        order.order_id, client_id, len(touchpoints)
    )


def _classify_source(session: Session) -> str:
    """Infer source from click IDs or referrer when UTM not present."""
    if session.fbclid:
        return "facebook"
    if session.gclid:
        return "google"
    if session.ttclid:
        return "tiktok"
    if session.msclkid:
        return "bing"
    if session.referrer:
        referrer = session.referrer.lower()
        if "google" in referrer:
            return "google"
        if "facebook" in referrer or "fb.com" in referrer:
            return "facebook"
        if "instagram" in referrer:
            return "instagram"
        if "tiktok" in referrer:
            return "tiktok"
        return "referral"
    return "direct"


if __name__ == "__main__":
    asyncio.run(run())
