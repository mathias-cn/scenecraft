from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import JobStatus, ProjectStage
from app.models.mixins import ProjectFKMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.project import Project


class Job(UUIDPrimaryKeyMixin, ProjectFKMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_project_id_job_group_id", "project_id", "job_group_id"),)

    stage: Mapped[ProjectStage] = mapped_column(
        pg_enum(ProjectStage, "project_stage"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    job_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"),
        nullable=False,
        default=JobStatus.QUEUED,
        server_default=text("'queued'::job_status"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=text("now()"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="jobs")
