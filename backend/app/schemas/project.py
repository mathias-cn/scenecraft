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
    DEFAULT_HIGGSFIELD_MODEL,
    DEFAULT_IMAGE_PROVIDER,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_OPENAI_MODEL,
    IMAGE_PROVIDERS,
    IMAGE_QUALITIES,
    OPENAI_IMAGE_MODELS,
)

AUDIO_GENERATION_MODES = ("elevenlabs", "user_upload")
SCENE_PACING_VALUES = ("short", "medium", "long")
_TRUE_VALUES = {True, 1, "1", "true", "True", "yes", "on"}


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
    model = merged.get("image_model")
    if name == "openai":
        chosen = str(model).strip() if model else DEFAULT_OPENAI_MODEL
        if chosen not in OPENAI_IMAGE_MODELS:
            raise ValueError("image_model OpenAI deve ser gpt-image-2 ou gpt-image-1-mini")
        merged["image_model"] = chosen
        quality = str(merged.get("image_quality") or DEFAULT_IMAGE_QUALITY).strip().lower()
        if quality not in IMAGE_QUALITIES:
            raise ValueError("image_quality deve ser low, medium ou high")
        merged["image_quality"] = quality
    else:
        merged["image_model"] = str(model).strip() if model and str(model).strip() else DEFAULT_HIGGSFIELD_MODEL
        merged.pop("image_quality", None)
    scene_style = merged.get("scene_style")
    if scene_style is not None:
        text = str(scene_style).strip()
        if text:
            merged["scene_style"] = text
        else:
            merged.pop("scene_style", None)
    for key in ("character_id", "scene_style_id"):
        raw = merged.get(key)
        if raw is None or str(raw).strip() == "":
            merged.pop(key, None)
            continue
        try:
            merged[key] = str(uuid.UUID(str(raw).strip()))
        except ValueError as exc:
            raise ValueError(f"{key} deve ser um UUID") from exc
    merged["reuse_original_audio"] = merged.get("reuse_original_audio") in _TRUE_VALUES
    pacing = str(merged.get("scene_pacing") or "medium").strip().lower()
    if pacing not in SCENE_PACING_VALUES:
        raise ValueError("scene_pacing deve ser 'short', 'medium' ou 'long'")
    merged["scene_pacing"] = pacing
    mode = str(merged.get("audio_generation_mode") or "elevenlabs").strip().lower()
    if mode not in AUDIO_GENERATION_MODES:
        raise ValueError("audio_generation_mode deve ser 'elevenlabs' ou 'user_upload'")
    merged["audio_generation_mode"] = "elevenlabs" if merged["reuse_original_audio"] else mode
    if "ken_burns" not in merged:
        merged["ken_burns"] = True
    else:
        merged["ken_burns"] = merged.get("ken_burns") in _TRUE_VALUES
    return merged


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    source_ref: str | None = Field(default=None, max_length=8000)
    target_language: str = Field(default="pt-BR", min_length=2, max_length=16)
    automation_config: dict[str, Any] = Field(default_factory=dict)
    image_provider: str | None = None
    character_id: uuid.UUID | None = None
    scene_style_id: uuid.UUID | None = None

    @field_validator("source_ref", "image_provider", mode="before")
    @classmethod
    def blank_to_none_optional(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("character_id", "scene_style_id", mode="before")
    @classmethod
    def blank_uuid_to_none(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        return value

    @model_validator(mode="after")
    def youtube_requires_ref(self):
        if self.source_type is SourceType.YOUTUBE_LINK and not self.source_ref:
            raise ValueError("source_ref é obrigatório para youtube_link")
        return self

    @model_validator(mode="after")
    def normalize_image_provider(self):
        config = dict(self.automation_config)
        if self.source_type is not SourceType.UPLOAD_AUDIO:
            config["reuse_original_audio"] = False
        self.automation_config = normalize_automation_config(
            config,
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


class ImageModelRead(BaseModel):
    id: str
    name: str


class VoiceRead(BaseModel):
    id: str
    name: str


class AudioGenerateRequest(BaseModel):
    voice_id: str = Field(min_length=1, max_length=128)


class VideoAssemblyExportRead(BaseModel):
    output_url: str | None = None


class ThumbnailsExportRead(BaseModel):
    file_url: str | None = None


class DescriptionsExportRead(BaseModel):
    text: str = ""
    tags: list[str] = Field(default_factory=list)


class ProjectExportRead(BaseModel):
    title: str
    video_assembly: VideoAssemblyExportRead
    thumbnails: ThumbnailsExportRead
    descriptions: DescriptionsExportRead


class DescriptionConfirmRequest(BaseModel):
    text: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def strip_description_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("descrição não pode ser vazia")
        return text


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
    cost_usd: Decimal | None = None

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
    cost_usd: Decimal | None = None

    model_config = {"from_attributes": True}


class DescriptionRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    text: str
    tags: list[str] = Field(default_factory=list)
    source: str
    cost_usd: Decimal | None = None

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


class CostPeriodRead(BaseModel):
    period: str
    total_usd: Decimal


class CostSeriesRead(BaseModel):
    timezone: str
    total_usd: Decimal
    daily: list[CostPeriodRead]
    monthly: list[CostPeriodRead]


class ProjectCostRead(BaseModel):
    project_id: uuid.UUID
    total_usd: Decimal
    scenes_usd: Decimal
    audio_tracks_usd: Decimal
    descriptions_usd: Decimal
    thumbnails_usd: Decimal
    llm_usd: Decimal
