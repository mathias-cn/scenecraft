from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import YoutubeUploadStatus
from app.models.mixins import ProjectFKMixin, UUIDPrimaryKeyMixin
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.project import Project


class YoutubeUpload(UUIDPrimaryKeyMixin, ProjectFKMixin, Base):
    __tablename__ = "youtube_uploads"

    youtube_video_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[YoutubeUploadStatus] = mapped_column(
        pg_enum(YoutubeUploadStatus, "youtube_upload_status"),
        nullable=False,
        default=YoutubeUploadStatus.PENDING,
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="youtube_uploads")
