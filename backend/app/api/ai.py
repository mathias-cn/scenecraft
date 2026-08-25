from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.providers.llm_client import LLMError, generate_titles

router = APIRouter(prefix="/api/ai", tags=["ai"])


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


@router.post("/generate-titles")
def generate_project_titles(payload: TitleGenerateRequest) -> TitleGenerateRead:
    try:
        titles = generate_titles(payload.draft_title)
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            if "OPENAI_API_KEY" in str(exc)
            else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return TitleGenerateRead(titles=titles)
