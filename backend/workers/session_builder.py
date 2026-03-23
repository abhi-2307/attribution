"""
Phase 3 + 4 — Queue Worker & Session Builder

Pulls events from pixel_event_queue (FOR UPDATE SKIP LOCKED),
groups them by (client_id, visitor_id), and upserts sessions with 30-min gap logic.

Run:
    python -m backend.workers.session_builder
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import AsyncSessionLocal
from ..models.events import PixelEventRaw, PixelEventQueue
from ..models.sessions import Session

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

BATCH_SIZE = 100
POLL_INTERVAL_SECONDS = 5
SESSION_GAP = timedelta(minutes=30)


# ─── Main Loop ────────────────────────────────────────────────────────────────

async def run():
    log.info("Session builder started — polling every %ds", POLL_INTERVAL_SECONDS)
    while True:
        try:
            await process_batch()
        except Exception as e:
            log.error("Batch processing error: %s", e, exc_info=True)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def process_batch():
    async with AsyncSessionLocal() as db:
        queue_rows = await _claim_batch(db)
        if not queue_rows:
            return

        event_ids = [row.event_id for row in queue_rows]
        queue_ids = [row.id for row in queue_rows]

        log.info("Processing %d events", len(event_ids))

        # Fetch the raw events
        result = await db.execute(
            select(PixelEventRaw)
            .where(PixelEventRaw.event_id.in_(event_ids))
            .order_by(PixelEventRaw.client_id, PixelEventRaw.visitor_id, PixelEventRaw.event_timestamp)
        )
        raw_events = result.scalars().all()

        # Group by (client_id, visitor_id)
        visitor_events: dict[tuple[str, str], list[PixelEventRaw]] = {}
        for ev in raw_events:
            key = (ev.client_id or "", ev.visitor_id)
            visitor_events.setdefault(key, []).append(ev)

        for (client_id, visitor_id), events in visitor_events.items():
            await _upsert_sessions(db, client_id, visitor_id, events)

        # Mark queue entries as done
        await db.execute(
            update(PixelEventQueue)
            .where(PixelEventQueue.id.in_(queue_ids))
            .values(status="done", processed_at=datetime.now(timezone.utc))
        )

        await db.commit()


async def _claim_batch(db: AsyncSession) -> list[PixelEventQueue]:
    """SELECT ... FOR UPDATE SKIP LOCKED — safe for multiple concurrent workers."""
    result = await db.execute(
        select(PixelEventQueue)
        .where(PixelEventQueue.status == "pending")
        .order_by(PixelEventQueue.created_at)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )
    rows = result.scalars().all()
    if rows:
        ids = [r.id for r in rows]
        await db.execute(
            update(PixelEventQueue)
            .where(PixelEventQueue.id.in_(ids))
            .values(status="processing")
        )
        await db.flush()
    return rows


async def _upsert_sessions(
    db: AsyncSession, client_id: str, visitor_id: str, events: list[PixelEventRaw]
):
    """
    For each (client_id, visitor_id) pair, fetch existing open sessions and either
    extend them or create new ones based on the 30-minute gap rule.
    """
    result = await db.execute(
        select(Session)
        .where(Session.client_id == client_id, Session.visitor_id == visitor_id)
        .order_by(Session.session_end.desc().nullslast())
        .limit(10)
    )
    existing_sessions: list[Session] = list(result.scalars().all())

    for ev in sorted(events, key=lambda e: e.event_timestamp):
        matched = _find_session(existing_sessions, ev.event_timestamp)

        if matched:
            matched.session_end = max(matched.session_end or ev.event_timestamp, ev.event_timestamp)
        else:
            new_session = Session(
                session_id=ev.session_id,
                client_id=client_id,
                visitor_id=visitor_id,
                session_start=ev.event_timestamp,
                session_end=ev.event_timestamp,
                landing_page=ev.url,
                referrer=ev.referrer,
                utm_source=ev.utm_source,
                utm_medium=ev.utm_medium,
                utm_campaign=ev.utm_campaign,
                utm_content=ev.utm_content,
                utm_term=ev.utm_term,
                fbclid=ev.fbclid,
                gclid=ev.gclid,
                ttclid=ev.ttclid,
                msclkid=ev.msclkid,
                created_at=datetime.now(timezone.utc),
            )
            db.add(new_session)
            existing_sessions.append(new_session)


def _find_session(
    sessions: list[Session], event_ts: datetime
) -> Session | None:
    """Return the session this event belongs to (within 30-min gap), or None."""
    for s in sessions:
        end = s.session_end or s.session_start
        if end and event_ts - end <= SESSION_GAP and event_ts >= s.session_start:
            return s
    return None


if __name__ == "__main__":
    asyncio.run(run())
