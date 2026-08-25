import type { SourceType } from "./types";

export const SOURCE_OPTIONS: { value: SourceType; label: string; hint: string }[] = [
  { value: "youtube_link", label: "YouTube", hint: "Cole o link do vídeo" },
  { value: "upload_video", label: "Vídeo", hint: "mp4, mov, webm…" },
  { value: "upload_audio", label: "Áudio", hint: "mp3, wav, m4a…" },
];

export const TRANSCRIPT_LANGUAGES = [
  { value: "original", label: "Original" },
  { value: "pt", label: "Português" },
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
] as const;

export type TranscriptLanguage = (typeof TRANSCRIPT_LANGUAGES)[number]["value"];

export const AUTOMATION_TOGGLES = [
  {
    key: "auto_transcribe",
    label: "Transcrição",
    pause: "transcript_review",
  },
  {
    key: "auto_scene_planning",
    label: "Planejamento de cenas",
    pause: "scene_review",
  },
  {
    key: "auto_media_gen",
    label: "Geração de mídia",
    pause: "media_review",
  },
  {
    key: "auto_audio",
    label: "Áudio",
    pause: "audio_review",
  },
  {
    key: "auto_render",
    label: "Render",
    pause: "render_review",
  },
  {
    key: "auto_thumbnail",
    label: "Thumbnail",
    pause: "após thumbnail_stage",
  },
  {
    key: "auto_description",
    label: "Descrição",
    pause: "ready_to_publish",
  },
] as const;

export type AutomationKey = (typeof AUTOMATION_TOGGLES)[number]["key"];

export type AutomationConfig = Record<AutomationKey, boolean>;

export function defaultAutomation(): AutomationConfig {
  return {
    auto_transcribe: false,
    auto_scene_planning: false,
    auto_media_gen: false,
    auto_audio: false,
    auto_render: false,
    auto_thumbnail: false,
    auto_description: false,
  };
}

export function toAutomationPayload(flags: AutomationConfig): Record<string, boolean> {
  return {
    ...flags,
    auto_media: flags.auto_media_gen,
    auto_publish: flags.auto_description,
  };
}
