from fastapi import APIRouter

from app.api.deps import DbDep
from app.core.daily_budget import configured_daily_limit_usd, daily_budget_snapshot
from app.core.project_cost import COST_TIMEZONE, load_cost_series
from app.schemas.project import CostBudgetRead, CostSeriesRead

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("/budget")
def get_cost_budget(db: DbDep) -> CostBudgetRead:
    return CostBudgetRead.model_validate(daily_budget_snapshot(db))


@router.get("")
def get_cost_series(db: DbDep) -> CostSeriesRead:
    series = load_cost_series(db)
    today = series["daily"][-1]["total_usd"] if series["daily"] else 0
    limit = configured_daily_limit_usd()
    return CostSeriesRead.model_validate(
        {
            **series,
            "timezone": series.get("timezone") or COST_TIMEZONE,
            "today_usd": today,
            "daily_limit_usd": limit,
            "limit_reached": limit is not None and today >= limit,
        }
    )
