"""
Phase 11 — Dashboard API

GET /attribution/summary        — revenue + ROAS by source/medium
GET /attribution/campaign       — revenue + ROAS by campaign
GET /journeys/order/{order_id}  — full journey for a specific order
GET /pixel/health               — tracking rate vs Shopify orders
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..models.orders import Order, OrderJourney
from ..workers.attribution_worker import AttributionResult

log = logging.getLogger(__name__)
router = APIRouter(tags=["attribution"])


# ─── Attribution Summary ──────────────────────────────────────────────────────

@router.get("/attribution/summary")
async def attribution_summary(
    model: str = Query("last_click", description="last_click | first_click | linear | time_decay"),
    days: int = Query(30, description="Lookback window in days"),
    db: AsyncSession = Depends(get_db),
):
    """Revenue and ROAS grouped by source / medium."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Pull attribution results joined to orders
    rows = await db.execute(
        text("""
            SELECT
                tp->>'source'   AS source,
                tp->>'medium'   AS medium,
                SUM((tp->>'credit')::numeric) AS attributed_revenue,
                COUNT(DISTINCT ar.order_id) AS orders
            FROM attribution_results ar,
                 jsonb_array_elements(ar.touchpoints_credited) AS tp
            JOIN orders o ON o.order_id = ar.order_id
            WHERE ar.model = :model
              AND o.shopify_created_at >= :since
            GROUP BY 1, 2
            ORDER BY attributed_revenue DESC
        """),
        {"model": model, "since": since},
    )
    results = [dict(r) for r in rows.mappings()]
    return {"model": model, "days": days, "data": results}


# ─── Campaign Attribution ─────────────────────────────────────────────────────

@router.get("/attribution/campaign")
async def attribution_campaign(
    model: str = Query("last_click"),
    days: int = Query(30),
    db: AsyncSession = Depends(get_db),
):
    """Revenue grouped by campaign, joined with ad spend if available."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = await db.execute(
        text("""
            SELECT
                tp->>'source'    AS source,
                tp->>'medium'    AS medium,
                tp->>'campaign'  AS campaign,
                SUM((tp->>'credit')::numeric) AS attributed_revenue,
                COUNT(DISTINCT ar.order_id) AS orders
            FROM attribution_results ar,
                 jsonb_array_elements(ar.touchpoints_credited) AS tp
            JOIN orders o ON o.order_id = ar.order_id
            WHERE ar.model = :model
              AND o.shopify_created_at >= :since
            GROUP BY 1, 2, 3
            ORDER BY attributed_revenue DESC
        """),
        {"model": model, "since": since},
    )
    results = [dict(r) for r in rows.mappings()]
    return {"model": model, "days": days, "data": results}


# ─── Order Journey ────────────────────────────────────────────────────────────

@router.get("/journeys/order/{order_id}")
async def get_order_journey(order_id: str, db: AsyncSession = Depends(get_db)):
    """Return the full customer journey (touchpoints) for a specific order."""
    result = await db.execute(
        select(OrderJourney).where(OrderJourney.order_id == order_id)
    )
    journey = result.scalar_one_or_none()

    if not journey:
        raise HTTPException(status_code=404, detail="Journey not found for this order")

    # Also pull attribution credits for all models
    credits_result = await db.execute(
        select(AttributionResult).where(AttributionResult.order_id == order_id)
    )
    credits = {r.model: r.touchpoints_credited for r in credits_result.scalars().all()}

    return {
        "order_id": order_id,
        "visitor_id": journey.visitor_id,
        "touchpoints": journey.touchpoints,
        "attribution": credits,
    }


# ─── Pixel Health ─────────────────────────────────────────────────────────────

@router.get("/pixel/health")
async def pixel_health(
    days: int = Query(7, description="Lookback window in days"),
    db: AsyncSession = Depends(get_db),
):
    """
    Compare Shopify orders vs pixel-tracked purchase events.
    Alert if tracking rate < 85%.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Total Shopify orders
    shopify_result = await db.execute(
        text("SELECT COUNT(*) FROM orders WHERE shopify_created_at >= :since"),
        {"since": since},
    )
    total_orders = shopify_result.scalar() or 0

    # Pixel-tracked purchases
    pixel_result = await db.execute(
        text("""
            SELECT COUNT(DISTINCT order_id)
            FROM order_journeys oj
            JOIN orders o ON o.order_id = oj.order_id
            WHERE o.shopify_created_at >= :since
              AND jsonb_array_length(oj.touchpoints) > 0
        """),
        {"since": since},
    )
    tracked_orders = pixel_result.scalar() or 0

    tracking_rate = (tracked_orders / total_orders) if total_orders > 0 else 0.0
    alert = tracking_rate < 0.85 and total_orders > 0

    return {
        "days": days,
        "total_shopify_orders": total_orders,
        "pixel_tracked_orders": tracked_orders,
        "tracking_rate": round(tracking_rate, 4),
        "alert": alert,
        "alert_message": "Tracking rate below 85% — check pixel installation" if alert else None,
    }
