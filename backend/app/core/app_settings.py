"""Configuração persistida (chave/valor) — teto diário e futuras flags."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting
from app.models.mixins import utcnow
from app.providers.pricing import as_usd

DAILY_COST_LIMIT_KEY = "daily_cost_limit_usd"


def get_setting(db: Session, key: str) -> str | None:
    row = db.get(AppSetting, key)
    value = getattr(row, "value", None) if row is not None else None
    if value is None:
        return None
    return str(value)


def set_setting(db: Session, key: str, value: str) -> AppSetting:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value, updated_at=utcnow())
        db.add(row)
        return row
    row.value = value
    row.updated_at = utcnow()
    return row


def delete_setting(db: Session, key: str) -> None:
    row = db.get(AppSetting, key)
    if row is not None:
        db.delete(row)


def parse_daily_limit(raw: str | None) -> Decimal | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        limit = as_usd(text)
    except (InvalidOperation, ValueError):
        return None
    if limit <= 0:
        return None
    return limit


def load_daily_cost_limit_usd(db: Session) -> Decimal | None:
    return parse_daily_limit(get_setting(db, DAILY_COST_LIMIT_KEY))


def save_daily_cost_limit_usd(db: Session, amount: Decimal | None) -> Decimal | None:
    """None ou ≤0 desliga o teto (remove a chave)."""
    if amount is None:
        delete_setting(db, DAILY_COST_LIMIT_KEY)
        return None
    limit = as_usd(amount)
    if limit <= 0:
        delete_setting(db, DAILY_COST_LIMIT_KEY)
        return None
    set_setting(db, DAILY_COST_LIMIT_KEY, str(limit))
    return limit
