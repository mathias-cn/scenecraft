import Link from "next/link";

import { ApiError, listCharacters } from "@/lib/api.server";
import { characterLabel } from "@/lib/character-ui";
import { formatCreatedAt } from "@/lib/project-ui";
import type { Character } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function CharactersPage() {
  let characters: Character[] = [];
  let error: string | null = null;
  try {
    characters = await listCharacters("approved");
  } catch (err) {
    error = err instanceof ApiError || err instanceof Error ? err.message : "Falha ao listar personagens";
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-white/45">Personagens aprovados, reutilizáveis nos projetos.</p>
        <Link
          href="/characters/new"
          className="rounded-md bg-brass-500 px-3 py-2 text-sm font-medium text-ink-950 transition hover:bg-brass-400"
        >
          Novo personagem
        </Link>
      </div>

      {error ? (
        <p className="rounded-md border border-red-500/30 bg-red-950/40 px-4 py-3 font-mono text-xs text-red-200">
          {error}
        </p>
      ) : characters.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 px-4 py-12 text-center">
          <p className="text-sm text-white/45">Nenhum personagem aprovado ainda.</p>
          <Link href="/characters/new" className="mt-3 inline-block text-sm text-brass-400 hover:text-brass-500">
            Criar o primeiro
          </Link>
        </div>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {characters.map((character) => (
            <li key={character.id}>
              <Link
                href={`/characters/${character.id}`}
                className="block overflow-hidden rounded-xl border border-white/[0.08] bg-ink-900 transition hover:border-brass-500/40"
              >
                {character.base_image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={character.base_image_url}
                    alt={characterLabel(character)}
                    className="aspect-[2/3] w-full object-cover bg-ink-950"
                  />
                ) : (
                  <div className="flex aspect-[2/3] items-center justify-center bg-ink-950 text-white/30">
                    <span className="font-mono text-[10px] uppercase">sem imagem</span>
                  </div>
                )}
                <div className="px-3 py-3">
                  <h2 className="line-clamp-2 text-sm font-medium text-white">{characterLabel(character)}</h2>
                  <p className="mt-1 font-mono text-[11px] text-white/40">{character.style?.name ?? "—"}</p>
                  <time className="mt-1 block font-mono text-[10px] text-white/30" dateTime={character.created_at}>
                    {formatCreatedAt(character.created_at)}
                  </time>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
