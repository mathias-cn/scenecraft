import uuid
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, Field, computed_field, field_validator

from app.models.enums import CharacterAssetType, CharacterStatus
from app.schemas.assets import SignedAssetModel, presign, stored_key_field
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


class CharacterAssetRead(SignedAssetModel):
    id: uuid.UUID
    character_id: uuid.UUID
    asset_type: CharacterAssetType
    stored_image_url: str = stored_key_field("image_url", required=True)
    cost_usd: Decimal | None = None
    created_at: datetime

    @computed_field
    @property
    def image_url(self) -> str:
        return presign(self.stored_image_url) or ""


class CharacterRead(SignedAssetModel):
    id: uuid.UUID
    description_prompt: str
    style_id: uuid.UUID
    style: StyleRead | None = None
    stored_reference_image_url: str | None = stored_key_field("reference_image_url")
    stored_base_image_url: str | None = stored_key_field("base_image_url")
    status: CharacterStatus
    created_at: datetime
    cost_usd: Decimal | None = None
    assets: list[CharacterAssetRead] = Field(default_factory=list)

    @computed_field
    @property
    def reference_image_url(self) -> str | None:
        return presign(self.stored_reference_image_url)

    @computed_field
    @property
    def base_image_url(self) -> str | None:
        return presign(self.stored_base_image_url)
