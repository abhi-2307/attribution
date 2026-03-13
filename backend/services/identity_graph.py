"""
Phase 5 — Identity Graph Service

Links visitor_id → email_hash → shopify_customer_id.
Called when a purchase event arrives (pixel or Shopify webhook).
"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.orders import IdentityGraph


def hash_email(email: str) -> str:
    """SHA-256 hash of lowercased, stripped email. Never store raw PII."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


async def stitch_identity(
    db: AsyncSession,
    visitor_id: str,
    email: str | None = None,
    shopify_customer_id: str | None = None,
):
    """
    Upsert identity graph row.
    If email_hash already maps to a different visitor_id, merge by updating
    the existing record's last_seen and linking the shopify_customer_id.
    """
    email_hash = hash_email(email) if email else None
    now = datetime.now(timezone.utc)

    # Try to find existing record by visitor_id
    result = await db.execute(
        select(IdentityGraph).where(IdentityGraph.visitor_id == visitor_id)
    )
    record = result.scalar_one_or_none()

    if record:
        record.last_seen = now
        if email_hash and not record.email_hash:
            record.email_hash = email_hash
        if shopify_customer_id and not record.shopify_customer_id:
            record.shopify_customer_id = shopify_customer_id
    else:
        # Check if email_hash already belongs to another visitor
        if email_hash:
            result2 = await db.execute(
                select(IdentityGraph).where(IdentityGraph.email_hash == email_hash)
            )
            existing_by_email = result2.scalar_one_or_none()
            if existing_by_email:
                # Update the existing record instead of creating a duplicate
                existing_by_email.last_seen = now
                if shopify_customer_id:
                    existing_by_email.shopify_customer_id = shopify_customer_id
                return

        new_record = IdentityGraph(
            visitor_id=visitor_id,
            email_hash=email_hash,
            shopify_customer_id=shopify_customer_id,
            first_seen=now,
            last_seen=now,
        )
        db.add(new_record)


async def resolve_visitor_by_email(db: AsyncSession, email: str) -> str | None:
    """Look up visitor_id from an email (e.g. from Shopify order)."""
    email_hash = hash_email(email)
    result = await db.execute(
        select(IdentityGraph.visitor_id).where(IdentityGraph.email_hash == email_hash)
    )
    row = result.scalar_one_or_none()
    return row
