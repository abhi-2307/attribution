"""
Shared FastAPI dependencies.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..models.clients import Client


async def get_client(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Client:
    """
    Resolve the calling client from the X-API-Key header.
    Used by reporting endpoints (attribution, journeys, health).
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")

    result = await db.execute(select(Client).where(Client.api_key == api_key))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return client
