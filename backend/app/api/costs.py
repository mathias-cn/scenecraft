from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import DbDep
from app.core.app_settings import save_daily_cost_limit_usd
from app.core.daily_budget import configured_daily_limit_usd, daily_budget_snapshot
from app.core.project_cost import COST_TIMEZONE, load_cost_series
from app.schemas.project import CostBudgetRead, CostSeriesRead

router = APIRouter(prefix="/api/costs", tags=["costs"])


class CostBudgetUpdate(BaseModel):
    daily_limit_usd: Decimal | None = Field(default=None, ge=0)


@router.get("/budget")
def get_cost_budget(db: DbDep) -> CostBudgetRead:
    return CostBudgetRead.model_validate(daily_budget_snapshot(db))


@router.patch("/budget")
def patch_cost_budget(payload: CostBudgetUpdate, db: DbDep) -> CostBudgetRead:
    save_daily_cost_limit_usd(db, payload.daily_limit_usd)
    db.commit()
    return CostBudgetRead.model_validate(daily_budget_snapshot(db))


@router.get("")
def get_cost_series(db: DbDep) -> CostSeriesRead:
    series = load_cost_series(db)
    today = series["daily"][-1]["total_usd"] if series["daily"] else 0
    limit = configured_daily_limit_usd(db)
    return CostSeriesRead.model_validate(
        {
            **series,
            "timezone": series.get("timezone") or COST_TIMEZONE,
            "today_usd": today,
            "daily_limit_usd": limit,
            "limit_reached": limit is not None and today >= limit,
        }
    )
