"""Converte object_key persistido em URL assinada na serialização da API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.storage import signed_asset_url


class SignedAssetModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def stored_key_field(orm_name: str, *, required: bool = False):
    if required:
        return Field(validation_alias=orm_name, exclude=True)
    return Field(default=None, validation_alias=orm_name, exclude=True)


def presign(value: str | None) -> str | None:
    return signed_asset_url(value)
