import type { Character, CharacterAssetType } from "./types";

export const CHARACTER_SET_SIZE = 9;

export const ASSET_LABEL: Record<CharacterAssetType, string> = {
  tpose_side: "T-pose (lado)",
  tpose_back: "T-pose (costas)",
  head_front: "Cabeça (frente)",
  head_side: "Cabeça (lado)",
  head_back: "Cabeça (costas)",
  sitting: "Sentado",
  holding_mug: "Com caneca",
  smiling: "Sorrindo",
  angry: "Bravo",
};

export const ASSET_ORDER: CharacterAssetType[] = [
  "tpose_side",
  "tpose_back",
  "head_front",
  "head_side",
  "head_back",
  "sitting",
  "holding_mug",
  "smiling",
  "angry",
];

export function characterLabel(character: Pick<Character, "description_prompt">): string {
  const line = character.description_prompt.trim().split(/\n/)[0] ?? "";
  if (line.length <= 72) return line || "Personagem";
  return `${line.slice(0, 69).trimEnd()}…`;
}
