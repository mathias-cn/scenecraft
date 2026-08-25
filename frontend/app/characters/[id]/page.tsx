import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CharacterPreview } from "@/components/character-preview";
import { ApiError, getCharacter } from "@/lib/api";
import { characterLabel } from "@/lib/character-ui";

export const dynamic = "force-dynamic";

type CharacterPageProps = {
  params: { id: string };
};

export async function generateMetadata({ params }: CharacterPageProps): Promise<Metadata> {
  try {
    const character = await getCharacter(params.id);
    return { title: characterLabel(character) };
  } catch {
    return { title: "Personagem" };
  }
}

export default async function CharacterPage({ params }: CharacterPageProps) {
  try {
    const character = await getCharacter(params.id);
    return (
      <div>
        <Link href="/characters" className="label-tech text-white/40 hover:text-brass-400">
          ← Personagens
        </Link>
        <div className="mt-4">
          <CharacterPreview initial={character} />
        </div>
      </div>
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
}
