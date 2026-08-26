"""Teto diário de gasto estimado: consulta o dia e bloqueia jobs pagos."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.app_settings import load_daily_cost_limit_usd
from app.core.project_cost import COST_TIMEZONE, load_today_cost
from app.models.enums import ProjectStage
from app.providers.pricing import as_usd

PAID_STAGES = frozenset(
    {
        ProjectStage.TRANSCRIBING,
        ProjectStage.SCENE_PLANNING,
        ProjectStage.GENERATING_MEDIA,
        ProjectStage.AUDIO_STAGE,
        ProjectStage.THUMBNAIL_STAGE,
        ProjectStage.DESCRIPTION_STAGE,
    }
)


class DailyCostLimitReached(Exception):
    """Gasto do dia atingiu ou ultrapassou o teto configurado."""

    def __init__(self, today_usd: Decimal, limit_usd: Decimal, timezone: str = COST_TIMEZONE) -> None:
        self.today_usd = as_usd(today_usd)
        self.limit_usd = as_usd(limit_usd)
        self.timezone = timezone
        super().__init__(
            "Limite diário de custo atingido "
            f"(hoje US$ {self.today_usd} de US$ {self.limit_usd}, {timezone}). "
            "Novos jobs pagos estão pausados até o próximo dia."
        )


def configured_daily_limit_usd(db: Session) -> Decimal | None:
    return load_daily_cost_limit_usd(db)


def is_paid_stage(stage: ProjectStage | None) -> bool:
    return stage in PAID_STAGES


def daily_budget_snapshot(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    today = load_today_cost(db, now=now)
    limit = configured_daily_limit_usd(db)
    reached = limit is not None and today >= limit
    return {
        "timezone": COST_TIMEZONE,
        "today_usd": today,
        "daily_limit_usd": limit,
        "limit_reached": reached,
    }


def assert_paid_job_allowed(db: Session, stage: ProjectStage | None = None) -> None:
    """No-op se o teto estiver desligado ou o estágio não for pago. Senão consulta o dia."""
    if stage is not None and not is_paid_stage(stage):
        return
    limit = configured_daily_limit_usd(db)
    if limit is None:
        return
    today = load_today_cost(db)
    if today >= limit:
        raise DailyCostLimitReached(today, limit)
