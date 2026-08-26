from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.api.deps import DbDep, require_owner
from app.core.daily_budget import DailyCostLimitReached, assert_paid_job_allowed
from app.models.title_suggestion import TitleSuggestion
from app.providers.llm_client import LLMError, generate_titles
from app.providers.pricing import as_usd

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[require_owner])


class TitleGenerateRequest(BaseModel):
    draft_title: str = Field(min_length=1, max_length=200)

    @field_validator("draft_title")
    @classmethod
    def strip_draft(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("draft_title vazio")
        return text


class TitleGenerateRead(BaseModel):
    titles: list[str]
    cost_usd: float | None = None


@router.post("/generate-titles")
def generate_project_titles(payload: TitleGenerateRequest, db: DbDep) -> TitleGenerateRead:
    try:
        assert_paid_job_allowed(db)
        titles = generate_titles(payload.draft_title)
    except DailyCostLimitReached as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            if "OPENAI_API_KEY" in str(exc)
            else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    cost = as_usd(getattr(titles, "cost_usd", 0))
    db.add(
        TitleSuggestion(
            draft_title=payload.draft_title,
            titles=list(titles),
            cost_usd=cost,
        )
    )
    db.commit()
    return TitleGenerateRead(titles=list(titles), cost_usd=float(cost))
