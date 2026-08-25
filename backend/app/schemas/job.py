import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import JobStatus, ProjectStage


class JobRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    stage: ProjectStage
    job_type: str
    status: JobStatus
    attempt_count: int
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}
