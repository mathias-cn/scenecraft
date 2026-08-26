from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ThumbnailSource
from app.models.mixins import ProjectFKMixin, UUIDPrimaryKeyMixin
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.project import Project


class Thumbnail(UUIDPrimaryKeyMixin, ProjectFKMixin, Base):
    __tablename__ = "thumbnails"

    source: Mapped[ThumbnailSource] = mapped_column(
        pg_enum(ThumbnailSource, "thumbnail_source"), nullable=False
    )
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    project: Mapped[Project] = relationship(back_populates="thumbnails")
