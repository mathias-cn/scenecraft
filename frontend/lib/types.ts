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
  | "completed"
  | "failed";

export type ProjectStatus =
  | "pending"
  | "running"
  | "paused_for_review"
  | "paused_cost_limit"
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
  character_id?: string;
  scene_style_id?: string;
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

export type CharacterStatus = "pending_approval" | "approved" | "rejected";

export type CharacterAssetType =
  | "tpose_side"
  | "tpose_back"
  | "head_front"
  | "head_side"
  | "head_back"
  | "sitting"
  | "holding_mug"
  | "smiling"
  | "angry";

export type CharacterAsset = {
  id: string;
  character_id: string;
  asset_type: CharacterAssetType;
  image_url: string;
  created_at: string;
};

export type Character = {
  id: string;
  description_prompt: string;
  style_id: string;
  style: Style | null;
  reference_image_url: string | null;
  base_image_url: string | null;
  status: CharacterStatus;
  created_at: string;
  assets: CharacterAsset[];
};

export type Scene = {
  id: string;
  index: number;
  start_ms: number;
  end_ms: number;
  source_segment_ids?: number[];
  visual_prompt: string;
  media_type: "image" | "video";
  media_url: string | null;
  status: string;
};

export type AudioTrack = {
  id: string;
  source: "original" | "generated" | "user_upload";
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
  tags: string[];
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
  paused_for_cost_limit?: boolean;
};

export type ProjectExport = {
  title: string;
  video_assembly: { output_url: string | null };
  thumbnails: { file_url: string | null };
  descriptions: { text: string; tags: string[] };
};

export type CostPeriod = {
  period: string;
  total_usd: string | number;
};

export type CostSeries = {
  timezone: string;
  total_usd: string | number;
  daily: CostPeriod[];
  monthly: CostPeriod[];
  today_usd: string | number;
  daily_limit_usd: string | number | null;
  limit_reached: boolean;
};

export type CostBudget = {
  timezone: string;
  today_usd: string | number;
  daily_limit_usd: string | number | null;
  limit_reached: boolean;
};
