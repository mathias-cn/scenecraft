from fastapi import APIRouter

from app.api.deps import DbDep
from app.core.project_cost import load_cost_series
from app.schemas.project import CostSeriesRead

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("")
def get_cost_series(db: DbDep) -> CostSeriesRead:
    return CostSeriesRead.model_validate(load_cost_series(db))
