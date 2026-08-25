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
from app.providers.image_provider import (
    DEFAULT_IMAGE_PROVIDER,
    IMAGE_PROVIDERS,
    IMAGE_QUALITIES,
    OPENAI_IMAGE_MODELS,
)


def normalize_automation_config(
    config: dict[str, Any] | None,
    *,
    image_provider: str | None = None,
) -> dict[str, Any]:
    """Garante image_provider válido e, se OpenAI, quality/model conhecidos."""
    merged = dict(config or {})
    raw = image_provider if image_provider not in (None, "") else merged.get("image_provider")
    name = str(raw or DEFAULT_IMAGE_PROVIDER).strip().lower()
    if name not in IMAGE_PROVIDERS:
        raise ValueError("image_provider deve ser 'higgsfield' ou 'openai'")
    merged["image_provider"] = name
    quality = merged.get("image_quality")
    if quality is not None and str(quality).strip().lower() not in IMAGE_QUALITIES:
        raise ValueError("image_quality deve ser low, medium ou high")
    if quality is not None:
        merged["image_quality"] = str(quality).strip().lower()
    model = merged.get("image_model")
    if name == "openai" and model:
        if str(model).strip() not in OPENAI_IMAGE_MODELS:
            raise ValueError("image_model OpenAI deve ser gpt-image-2 ou gpt-image-1-mini")
        merged["image_model"] = str(model).strip()
    elif model:
        merged["image_model"] = str(model).strip()
    scene_style = merged.get("scene_style")
    if scene_style is not None:
        text = str(scene_style).strip()
        if text:
            merged["scene_style"] = text
        else:
            merged.pop("scene_style", None)
    return merged


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    source_ref: str | None = Field(default=None, max_length=8000)
    target_language: str = Field(default="pt-BR", min_length=2, max_length=16)
    automation_config: dict[str, Any] = Field(default_factory=dict)
    image_provider: str | None = None

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

    @model_validator(mode="after")
    def normalize_image_provider(self):
        self.automation_config = normalize_automation_config(
            self.automation_config,
            image_provider=self.image_provider,
        )
        self.image_provider = self.automation_config["image_provider"]
        return self


class TranscriptSegmentPatch(BaseModel):
    id: uuid.UUID
    text_original: str | None = None
    text_translated: str | None = None


class TranscriptPatchRequest(BaseModel):
    segments: list[TranscriptSegmentPatch] = Field(default_factory=list)


class MediaSettingsPatch(BaseModel):
    image_model: str | None = None
    image_quality: str | None = None
    scene_style: str | None = None

    @field_validator("image_quality")
    @classmethod
    def quality_allowed(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        quality = value.strip().lower()
        if quality not in IMAGE_QUALITIES:
            raise ValueError("image_quality deve ser low, medium ou high")
        return quality


class ImageModelRead(BaseModel):
    id: str
    name: str


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


class ThumbnailRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    source: str
    file_url: str

    model_config = {"from_attributes": True}


class DescriptionRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    text: str
    source: str

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectRead):
    scenes: list[SceneRead] = Field(default_factory=list)
    audio_tracks: list[AudioTrackRead] = Field(default_factory=list)
    video_assembly: VideoAssemblyRead | None = None
    transcript_segments: list[TranscriptSegmentRead] = Field(default_factory=list)
    jobs: list[JobSummaryRead] = Field(default_factory=list)
    thumbnails: list[ThumbnailRead] = Field(default_factory=list)
    descriptions: list[DescriptionRead] = Field(default_factory=list)

    @model_validator(mode="after")
    def sort_nested(self):
        self.scenes = sorted(self.scenes, key=lambda scene: scene.index)
        self.transcript_segments = sorted(self.transcript_segments, key=lambda seg: seg.index)
        self.jobs = sorted(self.jobs, key=lambda job: job.created_at, reverse=True)
        return self
