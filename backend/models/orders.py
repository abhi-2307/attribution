from sqlalchemy import Column, Text, Numeric, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from .base import Base


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Text, primary_key=True)
    customer_email_hash = Column(Text)  # sha256 of email, never store raw PII
    order_value = Column(Numeric(12, 2))
    currency = Column(Text, default="USD")
    line_items = Column(JSONB)
    shopify_created_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_orders_customer_email_hash", "customer_email_hash"),
        Index("ix_orders_shopify_created_at", "shopify_created_at"),
        {"schema": "attribution"},
    )


class OrderJourney(Base):
    __tablename__ = "order_journeys"

    order_id = Column(Text, primary_key=True)
    visitor_id = Column(Text, nullable=False)

    # JSONB array of touchpoints:
    # [{"source":"facebook","medium":"cpc","campaign":"...", "session_id":"...", "session_start":"..."}]
    touchpoints = Column(JSONB, default=list)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_order_journeys_visitor_id", "visitor_id"),
        {"schema": "attribution"},
    )


class IdentityGraph(Base):
    __tablename__ = "identity_graph"

    visitor_id = Column(Text, primary_key=True)
    email_hash = Column(Text, unique=True, nullable=True)
    shopify_customer_id = Column(Text, nullable=True)
    first_seen = Column(TIMESTAMP(timezone=True))
    last_seen = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        Index("ix_identity_graph_email_hash", "email_hash"),
        Index("ix_identity_graph_shopify_customer_id", "shopify_customer_id"),
        {"schema": "attribution"},
    )
