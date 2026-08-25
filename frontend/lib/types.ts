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
  source_ref: string;
  target_language: string;
  automation_config?: Record<string, unknown>;
};
