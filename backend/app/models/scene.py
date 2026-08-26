from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import MediaType, SceneStatus
from app.models.mixins import ProjectFKMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.project import Project


class Scene(UUIDPrimaryKeyMixin, ProjectFKMixin, TimestampMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("project_id", "index", name="uq_scenes_project_index"),)

    index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    source_segment_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer),
        nullable=False,
        default=list,
        server_default=text("'{}'::integer[]"),
    )
    visual_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[MediaType] = mapped_column(pg_enum(MediaType, "media_type"), nullable=False)
    style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[SceneStatus] = mapped_column(
        pg_enum(SceneStatus, "scene_status"),
        nullable=False,
        default=SceneStatus.PENDING,
    )
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    project: Mapped[Project] = relationship(back_populates="scenes")
