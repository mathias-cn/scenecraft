import { apiDelete, apiGet, apiPatch, apiPost } from "./api-client";
import type {
  AdvanceResult,
  Character,
  CharacterStatus,
  ImageModelOption,
  Project,
  ProjectCreate,
  ProjectDetail,
  Style,
  TranscriptSegmentPatch,
} from "./types";

export { ApiError } from "./api-client";
export { getApiBaseUrl } from "./config";

export function listProjects() {
  return apiGet<Project[]>("/api/projects");
}

export function getProject(id: string) {
  return apiGet<ProjectDetail>(`/api/projects/${id}`);
}

export function createProject(payload: ProjectCreate, file?: File | null) {
  if (file) {
    const form = new FormData();
    form.append("title", payload.title);
    form.append("source_type", payload.source_type);
    form.append("target_language", payload.target_language);
    form.append("automation_config", JSON.stringify(payload.automation_config ?? {}));
    if (payload.source_ref) form.append("source_ref", payload.source_ref);
    if (payload.image_provider) form.append("image_provider", payload.image_provider);
    if (payload.character_id) form.append("character_id", payload.character_id);
    if (payload.scene_style_id) form.append("scene_style_id", payload.scene_style_id);
    form.append("file", file);
    return apiPost<Project>("/api/projects", form);
  }

  return apiPost<Project>("/api/projects", payload);
}

export function advanceProject(id: string, fromStage?: string) {
  return apiPost<AdvanceResult>(
    `/api/projects/${id}/advance`,
    fromStage ? { from_stage: fromStage } : {},
  );
}

export function retryProjectStage(id: string) {
  return apiPost<AdvanceResult>(`/api/projects/${id}/retry-stage`);
}

export function patchTranscript(id: string, segments: TranscriptSegmentPatch[]) {
  return apiPatch<ProjectDetail>(`/api/projects/${id}/transcript`, { segments });
}

export function listImageModels(projectId: string) {
  return apiGet<ImageModelOption[]>(`/api/projects/${projectId}/image-models`);
}

export function generateProjectAudio(id: string, voiceId: string) {
  return apiPost<ProjectDetail>(`/api/projects/${id}/audio/generate`, { voice_id: voiceId });
}

export function uploadProjectAudio(id: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiPost<ProjectDetail>(`/api/projects/${id}/audio/upload`, form);
}

export function listAudioVoices(projectId: string) {
  return apiGet<{ id: string; name: string }[]>(`/api/projects/${projectId}/audio/voices`);
}

export function patchMediaSettings(
  id: string,
  payload: { image_model?: string; image_quality?: string; scene_style?: string; scene_style_id?: string },
) {
  return apiPatch<ProjectDetail>(`/api/projects/${id}/media-settings`, payload);
}

export function listStyles(active?: boolean) {
  const query = active === undefined ? "" : `?active=${active ? "true" : "false"}`;
  return apiGet<Style[]>(`/api/styles${query}`);
}

export function createStyle(payload: { name: string; slug: string }) {
  return apiPost<Style>("/api/styles", payload);
}

export function patchStyle(id: string, active: boolean) {
  return apiPatch<Style>(`/api/styles/${id}`, { active });
}

export function deleteStyle(id: string) {
  return apiDelete<void>(`/api/styles/${id}`);
}

export function listCharacters(status?: CharacterStatus) {
  const query = status ? `?status=${status}` : "";
  return apiGet<Character[]>(`/api/characters${query}`);
}

export function getCharacter(id: string) {
  return apiGet<Character>(`/api/characters/${id}`);
}

export function createCharacter(
  payload: { description_prompt: string; style_id: string; reference_image_url?: string | null },
  file?: File | null,
) {
  if (file) {
    const form = new FormData();
    form.append("description_prompt", payload.description_prompt);
    form.append("style_id", payload.style_id);
    if (payload.reference_image_url) form.append("reference_image_url", payload.reference_image_url);
    form.append("file", file);
    return apiPost<Character>("/api/characters", form);
  }
  return apiPost<Character>("/api/characters", payload);
}

export function retryCharacter(
  id: string,
  payload: { description_prompt: string; style_id: string; reference_image_url?: string | null },
  file?: File | null,
) {
  if (file) {
    const form = new FormData();
    form.append("description_prompt", payload.description_prompt);
    form.append("style_id", payload.style_id);
    if (payload.reference_image_url) form.append("reference_image_url", payload.reference_image_url);
    form.append("file", file);
    return apiPost<Character>(`/api/characters/${id}/retry`, form);
  }
  return apiPost<Character>(`/api/characters/${id}/retry`, payload);
}

export function approveCharacter(id: string) {
  return apiPost<Character>(`/api/characters/${id}/approve`);
}

export function rejectCharacter(id: string) {
  return apiPost<Character>(`/api/characters/${id}/reject`);
}
