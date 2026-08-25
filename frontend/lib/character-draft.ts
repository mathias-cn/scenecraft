const DRAFT_KEY = "scenecraft.characterDraft";

export type CharacterDraft = {
  characterId?: string;
  description_prompt: string;
  style_id: string;
  reference_image_url?: string | null;
};

export function saveCharacterDraft(draft: CharacterDraft): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
}

export function readCharacterDraft(): CharacterDraft | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(DRAFT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as CharacterDraft;
    if (!parsed || typeof parsed.description_prompt !== "string") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearCharacterDraft(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(DRAFT_KEY);
}
