export type SourceType = "youtube_link" | "upload_video" | "upload_audio";

export type ProjectStage =
  | "ingest"
  | "transcribe"
  | "translate"
  | "scene"
  | "audio"
  | "assemble"
  | "thumbnail"
  | "describe"
  | "upload"
  | "complete";

export type ProjectStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

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
};
