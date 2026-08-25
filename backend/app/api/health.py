import redis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.queues import QUEUE_NAMES
from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    try:
        redis.Redis.from_url(settings.redis_url).ping()
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {exc}") from exc
    return {
        "status": "ok",
        "service": "scenecraft-api",
        "redis": settings.redis_url.split("@")[-1],
        "queues": list(QUEUE_NAMES),
    }
