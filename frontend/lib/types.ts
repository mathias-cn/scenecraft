export type SourceType = "youtube_link" | "upload_video" | "upload_audio";

export type ProjectStage =
  | "created"
  | "transcribing"
  | "transcript_review"
  | "scene_planning"
  | "scene_review"
  | "generating_media"
  | "media_review"
  | "audio_stage"
  | "audio_review"
  | "rendering"
  | "render_review"
  | "thumbnail_stage"
  | "description_stage"
  | "ready_to_publish"
  | "uploading"
  | "published"
  | "failed";

export type ProjectStatus =
  | "pending"
  | "running"
  | "paused_for_review"
  | "completed"
  | "failed"
  | "cancelled";

export type Project = {
  id: string;
  title: string;
  source_type: SourceType;
  source_ref: string;
  target_language: string;
  automation_config: Record<string, unknown>;
  current_stage: ProjectStage;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
};

export type ProjectCreate = {
  title: string;
  source_type: SourceType;
  source_ref?: string;
  target_language: string;
  automation_config?: Record<string, unknown>;
  image_provider?: "higgsfield" | "openai";
};

export type ImageModelOption = {
  id: string;
  name: string;
};

export type Style = {
  id: string;
  name: string;
  slug: string;
  active: boolean;
  created_at: string;
};

export type Scene = {
  id: string;
  index: number;
  start_ms: number;
  end_ms: number;
  visual_prompt: string;
  media_type: "image" | "video";
  media_url: string | null;
  status: string;
};

export type AudioTrack = {
  id: string;
  source: "original" | "generated";
  provider: string | null;
  file_url: string | null;
};

export type VideoAssembly = {
  id: string;
  ffmpeg_job_id: string | null;
  output_url: string | null;
  status: string;
};

export type TranscriptSegment = {
  id: string;
  index: number;
  start_ms: number;
  end_ms: number;
  text_original: string;
  text_translated: string | null;
  language: string;
};

export type TranscriptSegmentPatch = {
  id: string;
  text_original?: string;
  text_translated?: string | null;
};

export type Thumbnail = {
  id: string;
  file_url: string;
  source: string;
};

export type Description = {
  id: string;
  text: string;
  source: string;
};

export type JobSummary = {
  id: string;
  job_type: string;
  stage: ProjectStage;
  status: string;
  attempt_count: number;
  error: string | null;
};

export type ProjectDetail = Project & {
  scenes: Scene[];
  audio_tracks: AudioTrack[];
  transcript_segments: TranscriptSegment[];
  video_assembly: VideoAssembly | null;
  thumbnails: Thumbnail[];
  descriptions: Description[];
  jobs: JobSummary[];
};

export type AdvanceResult = {
  project_id: string;
  from_stage: ProjectStage;
  to_stage: ProjectStage;
  status: ProjectStatus;
  paused_for_review: boolean;
  dispatched_job_id: string | null;
};
