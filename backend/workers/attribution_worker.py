"""
Phase 9 — Attribution Worker

For each OrderJourney that hasn't been attributed yet,
run all four attribution models and store results.

Run:
    python -m backend.workers.attribution_worker
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import Column, Text, Numeric, TIMESTAMP, Index, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from ..db.database import AsyncSessionLocal
from ..models.base import Base
from ..models.orders import Order, OrderJourney
from ..services.attribution_engine import attribute_all_models

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

POLL_INTERVAL_SECONDS = 30
BATCH_SIZE = 50


# ─── Attribution Results Table ────────────────────────────────────────────────

class AttributionResult(Base):
    """Stores computed attribution per order, per model."""
    __tablename__ = "attribution_results"

    id = Column(Text, primary_key=True)  # order_id + model
    order_id = Column(Text, nullable=False)
    model = Column(Text, nullable=False)  # last_click | first_click | linear | time_decay
    touchpoints_credited = Column(JSONB)  # [{ session_id, source, medium, campaign, credit }]
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_attribution_results_order_id", "order_id"),
        Index("ix_attribution_results_model", "model"),
        {"schema": "attribution"},
    )


# ─── Main Loop ────────────────────────────────────────────────────────────────

async def run():
    log.info("Attribution worker started — polling every %ds", POLL_INTERVAL_SECONDS)
    while True:
        try:
            await process_batch()
        except Exception as e:
            log.error("Attribution worker error: %s", e, exc_info=True)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def process_batch():
    async with AsyncSessionLocal() as db:
        # Find journeys not yet attributed
        result = await db.execute(
            select(OrderJourney)
            .outerjoin(
                AttributionResult,
                OrderJourney.order_id == AttributionResult.order_id,
            )
            .where(AttributionResult.order_id.is_(None))
            .limit(BATCH_SIZE)
        )
        journeys: list[OrderJourney] = list(result.scalars().all())

        if not journeys:
            return

        log.info("Attributing %d journeys", len(journeys))

        order_ids = [j.order_id for j in journeys]
        orders_result = await db.execute(
            select(Order).where(Order.order_id.in_(order_ids))
        )
        orders_by_id = {o.order_id: o for o in orders_result.scalars().all()}

        for journey in journeys:
            order = orders_by_id.get(journey.order_id)
            if not order:
                continue
            await _attribute_journey(db, journey, order)

        await db.commit()


async def _attribute_journey(db, journey: OrderJourney, order: Order):
    conversion_time = order.shopify_created_at or datetime.now(timezone.utc)
    touchpoints = journey.touchpoints or []
    order_value = float(order.order_value or 0)

    all_results = attribute_all_models(touchpoints, order_value, conversion_time)

    for model_name, credits in all_results.items():
        record = AttributionResult(
            id=f"{journey.order_id}_{model_name}",
            order_id=journey.order_id,
            model=model_name,
            touchpoints_credited=credits,
        )
        db.add(record)

    log.info("Attributed order %s with %d touchpoints", journey.order_id, len(touchpoints))


if __name__ == "__main__":
    asyncio.run(run())
