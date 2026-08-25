from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import AudioTrackSource
from app.models.mixins import ProjectFKMixin, UUIDPrimaryKeyMixin
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.project import Project


class AudioTrack(UUIDPrimaryKeyMixin, ProjectFKMixin, Base):
    __tablename__ = "audio_tracks"

    source: Mapped[AudioTrackSource] = mapped_column(
        pg_enum(AudioTrackSource, "audio_track_source"), nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_timestamps: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    project: Mapped[Project] = relationship(back_populates="audio_tracks")
