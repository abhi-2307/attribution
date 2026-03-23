from sqlalchemy import Column, Text, TIMESTAMP
from sqlalchemy.sql import func
from .base import Base


class Client(Base):
    __tablename__ = "clients"

    client_id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    api_key = Column(Text, unique=True, nullable=False)
    shopify_webhook_secret = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = {"schema": "attribution"}
