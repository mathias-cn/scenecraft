import enum


class SourceType(str, enum.Enum):
    YOUTUBE_LINK = "youtube_link"
    UPLOAD_VIDEO = "upload_video"
    UPLOAD_AUDIO = "upload_audio"


class ProjectStage(str, enum.Enum):
    INGEST = "ingest"
    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"
    SCENE = "scene"
    AUDIO = "audio"
    ASSEMBLE = "assemble"
    THUMBNAIL = "thumbnail"
    DESCRIBE = "describe"
    UPLOAD = "upload"
    COMPLETE = "complete"


class ProjectStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
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
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
