export type JobStatus =
  | "pending"
  | "scripting"
  | "voicing"
  | "generating"
  | "uploading"
  | "completed"
  | "failed";

export type Job = {
  id: string;
  title: string;
  prompt: string;
  status: JobStatus;
  script: string | null;
  voice_url: string | null;
  video_url: string | null;
  youtube_url: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type JobCreate = {
  title: string;
  prompt: string;
};
