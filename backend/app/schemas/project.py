import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import (
    AssemblyStatus,
    AudioTrackSource,
    JobStatus,
    MediaType,
    ProjectStage,
    ProjectStatus,
    SceneStatus,
    SourceType,
)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    source_ref: str | None = Field(default=None, max_length=8000)
    target_language: str = Field(default="pt-BR", min_length=2, max_length=16)
    automation_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_ref", mode="before")
    @classmethod
    def blank_source_ref_to_none(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def youtube_requires_ref(self):
        if self.source_type is SourceType.YOUTUBE_LINK and not self.source_ref:
            raise ValueError("source_ref é obrigatório para youtube_link")
        return self


class AdvanceRequest(BaseModel):
    from_stage: ProjectStage | None = None


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


class SceneRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    index: int
    start_ms: int
    end_ms: int
    source_segment_ids: list[int] = Field(default_factory=list)
    visual_prompt: str
    media_type: MediaType
    style: str | None = None
    media_url: str | None = None
    generation_provider: str | None = None
    status: SceneStatus
    cost_usd: Decimal | None = None

    model_config = {"from_attributes": True}


class AudioTrackRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    source: AudioTrackSource
    provider: str | None = None
    voice_id: str | None = None
    file_url: str | None = None
    word_timestamps: dict[str, Any] | list[Any] | None = None

    model_config = {"from_attributes": True}


class VideoAssemblyRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    ffmpeg_job_id: str | None = None
    output_url: str | None = None
    status: AssemblyStatus
    render_config: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class TranscriptSegmentRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    index: int
    start_ms: int
    end_ms: int
    text_original: str
    text_translated: str | None = None
    language: str

    model_config = {"from_attributes": True}


class JobSummaryRead(BaseModel):
    id: uuid.UUID
    job_type: str
    job_group_id: uuid.UUID | None = None
    stage: ProjectStage
    status: JobStatus
    attempt_count: int
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectRead):
    scenes: list[SceneRead] = Field(default_factory=list)
    audio_tracks: list[AudioTrackRead] = Field(default_factory=list)
    video_assembly: VideoAssemblyRead | None = None
    transcript_segments: list[TranscriptSegmentRead] = Field(default_factory=list)
    jobs: list[JobSummaryRead] = Field(default_factory=list)

    @model_validator(mode="after")
    def sort_nested(self):
        self.scenes = sorted(self.scenes, key=lambda scene: scene.index)
        self.transcript_segments = sorted(self.transcript_segments, key=lambda seg: seg.index)
        self.jobs = sorted(self.jobs, key=lambda job: job.created_at, reverse=True)
        return self
