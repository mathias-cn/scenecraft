import uuid
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import CharacterAssetType, CharacterStatus
from app.schemas.style import StyleRead


class CharacterCreate(BaseModel):
    description_prompt: str = Field(min_length=1, max_length=4000)
    style_id: uuid.UUID
    reference_image_url: str | None = None

    @field_validator("description_prompt")
    @classmethod
    def strip_prompt(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("description_prompt é obrigatório")
        return text

    @field_validator("reference_image_url", mode="before")
    @classmethod
    def blank_url_to_none(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class CharacterAssetRead(BaseModel):
    id: uuid.UUID
    character_id: uuid.UUID
    asset_type: CharacterAssetType
    image_url: str
    cost_usd: Decimal | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CharacterRead(BaseModel):
    id: uuid.UUID
    description_prompt: str
    style_id: uuid.UUID
    style: StyleRead | None = None
    reference_image_url: str | None
    base_image_url: str | None
    status: CharacterStatus
    created_at: datetime
    cost_usd: Decimal | None = None
    assets: list[CharacterAssetRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}
