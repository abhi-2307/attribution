from sqlalchemy import Column, Text, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .base import Base


class PixelEventRaw(Base):
    __tablename__ = "pixel_events_raw"

    event_id = Column(UUID(as_uuid=True), primary_key=True)
    visitor_id = Column(Text, nullable=False)
    session_id = Column(Text, nullable=False)

    event_name = Column(Text, nullable=False)

    url = Column(Text)
    path = Column(Text)
    referrer = Column(Text)

    utm_source = Column(Text)
    utm_medium = Column(Text)
    utm_campaign = Column(Text)
    utm_content = Column(Text)
    utm_term = Column(Text)

    fbclid = Column(Text)
    gclid = Column(Text)
    ttclid = Column(Text)
    msclkid = Column(Text)

    user_agent = Column(Text)
    ip_address = Column(Text)

    event_timestamp = Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_pixel_events_raw_visitor_id", "visitor_id"),
        Index("ix_pixel_events_raw_session_id", "session_id"),
        Index("ix_pixel_events_raw_event_timestamp", "event_timestamp"),
        Index("ix_pixel_events_raw_event_name", "event_name"),
        {"schema": "attribution"},
    )


class PixelEventQueue(Base):
    """
    Lightweight queue table used instead of Kafka.
    Workers poll this table using SELECT ... FOR UPDATE SKIP LOCKED.
    """
    __tablename__ = "pixel_event_queue"

    id = Column(UUID(as_uuid=True), primary_key=True)
    event_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(Text, default="pending")  # pending | processing | done | failed
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    processed_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        Index("ix_pixel_event_queue_status", "status"),
        Index("ix_pixel_event_queue_created_at", "created_at"),
        {"schema": "attribution"},
    )
