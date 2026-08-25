import enum


class SourceType(str, enum.Enum):
    YOUTUBE_LINK = "youtube_link"
    UPLOAD_VIDEO = "upload_video"
    UPLOAD_AUDIO = "upload_audio"


class ProjectStage(str, enum.Enum):
    CREATED = "created"
    TRANSCRIBING = "transcribing"
    TRANSCRIPT_REVIEW = "transcript_review"
    SCENE_PLANNING = "scene_planning"
    SCENE_REVIEW = "scene_review"
    GENERATING_MEDIA = "generating_media"
    MEDIA_REVIEW = "media_review"
    AUDIO_STAGE = "audio_stage"
    AUDIO_REVIEW = "audio_review"
    RENDERING = "rendering"
    RENDER_REVIEW = "render_review"
    THUMBNAIL_STAGE = "thumbnail_stage"
    DESCRIPTION_STAGE = "description_stage"
    READY_TO_PUBLISH = "ready_to_publish"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"


class ProjectStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED_FOR_REVIEW = "paused_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


class SceneStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class AudioTrackSource(str, enum.Enum):
    ORIGINAL = "original"
    GENERATED = "generated"


class AssemblyStatus(str, enum.Enum):
    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class ThumbnailSource(str, enum.Enum):
    GENERATED = "generated"
    UPLOADED = "uploaded"


class DescriptionSource(str, enum.Enum):
    GENERATED = "generated"
    MANUAL = "manual"


class YoutubeUploadStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
