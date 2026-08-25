from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ProjectStage, ProjectStatus, SourceType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.audio_track import AudioTrack
    from app.models.description import Description
    from app.models.job import Job
    from app.models.scene import Scene
    from app.models.thumbnail import Thumbnail
    from app.models.transcript_segment import TranscriptSegment
    from app.models.video_assembly import VideoAssembly
    from app.models.youtube_upload import YoutubeUpload


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        pg_enum(SourceType, "source_type"), nullable=False
    )
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    target_language: Mapped[str] = mapped_column(String(16), nullable=False, default="pt-BR")
    automation_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    current_stage: Mapped[ProjectStage] = mapped_column(
        pg_enum(ProjectStage, "project_stage"),
        nullable=False,
        default=ProjectStage.CREATED,
    )
    status: Mapped[ProjectStatus] = mapped_column(
        pg_enum(ProjectStatus, "project_status"),
        nullable=False,
        default=ProjectStatus.PENDING,
    )

    transcript_segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    scenes: Mapped[list[Scene]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Scene.index",
    )
    audio_tracks: Mapped[list[AudioTrack]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    video_assemblies: Mapped[list[VideoAssembly]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    thumbnails: Mapped[list[Thumbnail]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    descriptions: Mapped[list[Description]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Description.created_at",
    )
    youtube_uploads: Mapped[list[YoutubeUpload]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Job.created_at",
    )

    @property
    def video_assembly(self) -> VideoAssembly | None:
        if not self.video_assemblies:
            return None
        return self.video_assemblies[-1]
