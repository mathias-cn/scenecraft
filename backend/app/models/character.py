from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import CharacterAssetType, CharacterStatus
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.style import Style


class Character(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (Index("ix_characters_status", "status"),)

    description_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    style_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("styles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reference_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CharacterStatus] = mapped_column(
        pg_enum(CharacterStatus, "character_status"),
        nullable=False,
        default=CharacterStatus.PENDING_APPROVAL,
        server_default=text("'pending_approval'::character_status"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=text("now()"),
        nullable=False,
    )

    style: Mapped[Style] = relationship(back_populates="characters")
    assets: Mapped[list[CharacterAsset]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        order_by="CharacterAsset.created_at",
    )


class CharacterAsset(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "character_assets"
    __table_args__ = (
        UniqueConstraint("character_id", "asset_type", name="uq_character_assets_character_type"),
    )

    character_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_type: Mapped[CharacterAssetType] = mapped_column(
        pg_enum(CharacterAssetType, "character_asset_type"),
        nullable=False,
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=text("now()"),
        nullable=False,
    )

    character: Mapped[Character] = relationship(back_populates="assets")
