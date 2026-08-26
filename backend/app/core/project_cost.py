"""Custos estimados: total por projeto e série agregada por dia/mês."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from app.core.state_machine import ProjectNotFound
from app.models.audio_track import AudioTrack
from app.models.description import Description
from app.models.project import Project
from app.models.scene import Scene
from app.models.thumbnail import Thumbnail
from app.providers.pricing import add_usd, as_usd

COST_TIMEZONE = "America/Sao_Paulo"
DAILY_WINDOW_DAYS = 30
MONTHLY_WINDOW_MONTHS = 12
_SAO_PAULO_OFFSET = timezone(timedelta(hours=-3))


def _zone(tz_name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        if tz_name == COST_TIMEZONE:
            return _SAO_PAULO_OFFSET
        return timezone.utc


def _items_cost(items: Any) -> Any:
    return add_usd(*(getattr(item, "cost_usd", None) for item in (items or [])))


def project_cost_breakdown(project: Any) -> dict[str, Any]:
    scenes_usd = _items_cost(getattr(project, "scenes", None))
    audio_usd = _items_cost(getattr(project, "audio_tracks", None))
    descriptions_usd = _items_cost(getattr(project, "descriptions", None))
    thumbnails_usd = _items_cost(getattr(project, "thumbnails", None))
    llm_usd = as_usd(getattr(project, "llm_cost_usd", None))
    return {
        "project_id": project.id,
        "total_usd": add_usd(scenes_usd, audio_usd, descriptions_usd, thumbnails_usd, llm_usd),
        "scenes_usd": scenes_usd,
        "audio_tracks_usd": audio_usd,
        "descriptions_usd": descriptions_usd,
        "thumbnails_usd": thumbnails_usd,
        "llm_usd": llm_usd,
    }


def load_project_cost(project_id: UUID | str, db: Session) -> dict[str, Any]:
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    project = db.get(Project, pid)
    if project is None:
        raise ProjectNotFound(str(pid))
    return project_cost_breakdown(project)


def _cost_select(spent_at, amount):
    return select(spent_at.label("spent_at"), amount.label("cost_usd")).where(
        amount.isnot(None),
        amount > 0,
    )


def cost_entries_union():
    """UNION ALL de (spent_at, cost_usd) das tabelas com gasto estimado."""
    parts = (
        _cost_select(Scene.updated_at, Scene.cost_usd),
        _cost_select(AudioTrack.created_at, AudioTrack.cost_usd),
        _cost_select(Description.created_at, Description.cost_usd),
        _cost_select(Thumbnail.created_at, Thumbnail.cost_usd),
        _cost_select(Project.created_at, Project.llm_cost_usd),
    )
    return union_all(*parts)


def daily_cost_totals_stmt(tz: str = COST_TIMEZONE):
    """Soma cost_usd agrupando pelo dia local (America/Sao_Paulo por padrão)."""
    entries = cost_entries_union().subquery("cost_entries")
    local_day = func.date_trunc("day", func.timezone(tz, entries.c.spent_at)).label("period")
    return (
        select(local_day, func.coalesce(func.sum(entries.c.cost_usd), 0).label("total_usd"))
        .group_by(local_day)
        .order_by(local_day)
    )


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def build_cost_series(
    daily_rows: Sequence[tuple[Any, Any]],
    *,
    now: datetime | None = None,
    tz_name: str = COST_TIMEZONE,
) -> dict[str, Any]:
    """Monta janelas diária (30 dias) e mensal (12 meses) a partir de totais por dia."""
    tz = _zone(tz_name)
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc).astimezone(tz)
    else:
        current = current.astimezone(tz)
    today = current.date()

    by_day: dict[date, Any] = {}
    for period, total in daily_rows:
        day = _as_date(period)
        by_day[day] = add_usd(by_day.get(day), total)

    all_time = add_usd(*by_day.values()) if by_day else as_usd(0)

    daily = []
    for offset in range(DAILY_WINDOW_DAYS - 1, -1, -1):
        day = today - timedelta(days=offset)
        daily.append({"period": day.isoformat(), "total_usd": as_usd(by_day.get(day))})

    by_month: dict[tuple[int, int], Any] = {}
    for day, amount in by_day.items():
        key = (day.year, day.month)
        by_month[key] = add_usd(by_month.get(key), amount)

    monthly = []
    for back in range(MONTHLY_WINDOW_MONTHS - 1, -1, -1):
        year, month = _shift_month(today.year, today.month, -back)
        monthly.append(
            {
                "period": f"{year:04d}-{month:02d}",
                "total_usd": as_usd(by_month.get((year, month))),
            }
        )

    return {
        "timezone": tz_name,
        "total_usd": all_time,
        "daily": daily,
        "monthly": monthly,
    }


def load_cost_series(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    rows = db.execute(daily_cost_totals_stmt()).all()
    daily_rows = [(row.period, row.total_usd) for row in rows]
    return build_cost_series(daily_rows, now=now)
