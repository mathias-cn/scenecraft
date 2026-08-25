import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ProjectStage, ProjectStatus, SourceType


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    source_ref: str = Field(min_length=1, max_length=8000)
    target_language: str = Field(default="pt-BR", min_length=2, max_length=16)
    automation_config: dict[str, Any] = Field(default_factory=dict)


class AdvanceRequest(BaseModel):
    from_stage: ProjectStage


class AdvanceRead(BaseModel):
    project_id: uuid.UUID
    from_stage: ProjectStage
    to_stage: ProjectStage
    status: ProjectStatus
    paused_for_review: bool
    dispatched_job_id: uuid.UUID | None = None
    auto_advanced: bool = False


class ProjectRead(BaseModel):
    id: uuid.UUID
    title: str
    source_type: SourceType
    source_ref: str
    target_language: str
    automation_config: dict[str, Any]
    current_stage: ProjectStage
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
