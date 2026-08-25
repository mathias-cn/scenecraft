from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import AssemblyStatus
from app.models.mixins import ProjectFKMixin, UUIDPrimaryKeyMixin
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.project import Project


class VideoAssembly(UUIDPrimaryKeyMixin, ProjectFKMixin, Base):
    __tablename__ = "video_assembly"

    ffmpeg_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    output_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AssemblyStatus] = mapped_column(
        pg_enum(AssemblyStatus, "assembly_status"),
        nullable=False,
        default=AssemblyStatus.PENDING,
    )
    render_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    project: Mapped[Project] = relationship(back_populates="video_assemblies")
