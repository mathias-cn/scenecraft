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

export type ImageProviderName = "higgsfield" | "openai";

export const IMAGE_PROVIDERS: { value: ImageProviderName; label: string; hint: string }[] = [
  { value: "higgsfield", label: "Higgsfield", hint: "Catálogo de modelos da Higgsfield" },
  { value: "openai", label: "OpenAI Image", hint: "gpt-image-2 e gpt-image-1-mini" },
];

export const OPENAI_IMAGE_MODELS = [
  { id: "gpt-image-2", name: "GPT Image 2" },
  { id: "gpt-image-1-mini", name: "GPT Image 1 Mini" },
] as const;

export const IMAGE_QUALITIES = [
  { id: "low", name: "Low" },
  { id: "medium", name: "Medium" },
  { id: "high", name: "High" },
] as const;

export type ImageQuality = (typeof IMAGE_QUALITIES)[number]["id"];

export const DEFAULT_OPENAI_MODEL = "gpt-image-2";
export const DEFAULT_IMAGE_QUALITY: ImageQuality = "medium";

export type AudioGenerationMode = "elevenlabs" | "user_upload";

export const AUDIO_GENERATION_MODES: { value: AudioGenerationMode; label: string }[] = [
  { value: "elevenlabs", label: "ElevenLabs" },
  { value: "user_upload", label: "Áudio (upload próprio)" },
];

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
    pause: "thumbnail_stage",
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

export function toAutomationPayload(
  flags: AutomationConfig,
  imageProvider: ImageProviderName = "higgsfield",
  sceneStyleId?: string,
  characterId?: string,
    extras?: {
    reuseOriginalAudio?: boolean;
    audioGenerationMode?: AudioGenerationMode;
    imageModel?: string;
    imageQuality?: ImageQuality;
    kenBurns?: boolean;
  },
): Record<string, unknown> {
  const reuse = Boolean(extras?.reuseOriginalAudio);
  const imageModel = extras?.imageModel?.trim();
  return {
    ...flags,
    auto_media: flags.auto_media_gen,
    auto_publish: flags.auto_description,
    image_provider: imageProvider,
    reuse_original_audio: reuse,
    audio_generation_mode: reuse ? "elevenlabs" : (extras?.audioGenerationMode ?? "elevenlabs"),
    ken_burns: extras?.kenBurns !== false,
    ...(imageModel ? { image_model: imageModel } : {}),
    ...(imageProvider === "openai" ? { image_quality: extras?.imageQuality ?? DEFAULT_IMAGE_QUALITY } : {}),
    ...(characterId ? { character_id: characterId } : {}),
    ...(sceneStyleId ? { scene_style_id: sceneStyleId } : {}),
  };
}

export function imageProviderOf(config: Record<string, unknown> | undefined): ImageProviderName {
  return config?.image_provider === "openai" ? "openai" : "higgsfield";
}

export function configString(config: Record<string, unknown> | undefined, key: string): string | null {
  const value = config?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function configBool(config: Record<string, unknown> | undefined, key: string): boolean {
  const value = config?.[key];
  return value === true || value === 1 || value === "1" || value === "true" || value === "True";
}

export function audioGenerationModeOf(config: Record<string, unknown> | undefined): AudioGenerationMode {
  return config?.audio_generation_mode === "user_upload" ? "user_upload" : "elevenlabs";
}

export function kenBurnsEnabled(config: Record<string, unknown> | undefined): boolean {
  if (config == null || !("ken_burns" in config)) return true;
  return configBool(config, "ken_burns");
}
