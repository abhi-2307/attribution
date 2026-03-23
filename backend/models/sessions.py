from sqlalchemy import Column, Text, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class Session(Base):
    __tablename__ = "sessions"

    session_id = Column(Text, primary_key=True)
    visitor_id = Column(Text, nullable=False)

    session_start = Column(TIMESTAMP(timezone=True), nullable=False)
    session_end = Column(TIMESTAMP(timezone=True))

    landing_page = Column(Text)
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

    page_view_count = Column(Text)  # stored as int-like for simplicity
    created_at = Column(TIMESTAMP(timezone=True))

    client_id = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_sessions_visitor_id", "visitor_id"),
        Index("ix_sessions_session_start", "session_start"),
        Index("ix_sessions_utm_campaign", "utm_campaign"),
        Index("ix_sessions_client_id", "client_id"),
        {"schema": "attribution"},
    )
