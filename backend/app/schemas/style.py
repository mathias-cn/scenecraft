import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def normalize_style_slug(value: str) -> str:
    slug = (value or "").strip().lower().replace("_", "-")
    return slug


class StyleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("name é obrigatório")
        return text

    @field_validator("slug")
    @classmethod
    def slug_format(cls, value: str) -> str:
        slug = normalize_style_slug(value)
        if not slug:
            raise ValueError("slug é obrigatório")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
        if any(char not in allowed for char in slug) or slug.startswith("-") or slug.endswith("-"):
            raise ValueError("slug deve ser minúsculo, com hífens (ex: ilustracao-digital)")
        if "--" in slug:
            raise ValueError("slug não pode ter hífens consecutivos")
        return slug


class StylePatch(BaseModel):
    active: bool


class StyleRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
