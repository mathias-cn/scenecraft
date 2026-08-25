"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { approveCharacter, getCharacter, rejectCharacter } from "@/lib/api";
import { saveCharacterDraft } from "@/lib/character-draft";
import { ASSET_LABEL, ASSET_ORDER, CHARACTER_SET_SIZE, characterLabel } from "@/lib/character-ui";
import type { Character } from "@/lib/types";

type CharacterPreviewProps = {
  initial: Character;
};

export function CharacterPreview({ initial }: CharacterPreviewProps) {
  const router = useRouter();
  const [character, setCharacter] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pending = character.status === "pending_approval";
  const approved = character.status === "approved";
  const waitingBase = pending && !character.base_image_url;
  const setCount = character.assets.length;
  const setComplete = approved && setCount >= CHARACTER_SET_SIZE;

  useEffect(() => {
    const shouldPoll = waitingBase || (approved && !setComplete);
    if (!shouldPoll) return undefined;
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await getCharacter(character.id);
        if (!cancelled) setCharacter(next);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Falha ao atualizar o personagem");
        }
      }
    };
    const id = window.setInterval(() => void tick(), 2000);
    void tick();
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [character.id, waitingBase, approved, setComplete]);

  async function onApprove() {
    setBusy(true);
    setError(null);
    try {
      setCharacter(await approveCharacter(character.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível aprovar");
    } finally {
      setBusy(false);
    }
  }

  async function onReject() {
    setBusy(true);
    setError(null);
    try {
      const rejected = await rejectCharacter(character.id);
      saveCharacterDraft({
        characterId: rejected.id,
        description_prompt: rejected.description_prompt,
        style_id: rejected.style_id,
        reference_image_url: rejected.reference_image_url,
      });
      router.push("/characters/new");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível recusar");
      setBusy(false);
    }
  }

  function resumeEdit() {
    saveCharacterDraft({
      characterId: character.id,
      description_prompt: character.description_prompt,
      style_id: character.style_id,
      reference_image_url: character.reference_image_url,
    });
    router.push("/characters/new");
  }

  const assetsByType = new Map(character.assets.map((asset) => [asset.asset_type, asset]));

  return (
    <div className="mx-auto max-w-3xl">
      <p className="label-tech">{character.style?.name ?? "sem estilo"}</p>
      <h2 className="mt-2 text-xl font-medium tracking-tight text-white">{characterLabel(character)}</h2>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-white/50">{character.description_prompt}</p>

      {waitingBase ? (
        <div className="mt-8 rounded-xl border border-dashed border-white/10 px-4 py-16 text-center">
          <p className="text-sm text-white/70">Gerando imagem base…</p>
          <p className="mt-2 font-mono text-[11px] text-white/35">Isso pode levar alguns segundos.</p>
        </div>
      ) : null}

      {character.base_image_url ? (
        <figure className="mt-8 overflow-hidden rounded-xl border border-white/[0.08] bg-ink-900">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={character.base_image_url} alt={characterLabel(character)} className="mx-auto max-h-[32rem] w-full object-contain bg-ink-950" />
          <figcaption className="px-4 py-3 font-mono text-[11px] text-white/35">Imagem base</figcaption>
        </figure>
      ) : null}

      {pending && character.base_image_url ? (
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            disabled={busy}
            onClick={() => void onApprove()}
            className="rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50"
          >
            {busy ? "Aprovando…" : "Aprovar"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onReject()}
            className="rounded-md border border-white/15 px-4 py-2.5 text-sm text-white/80 transition hover:bg-white/5 disabled:opacity-50"
          >
            Recusar
          </button>
        </div>
      ) : null}

      {character.status === "rejected" ? (
        <div className="mt-6">
          <p className="text-sm text-white/45">Este personagem foi recusado. Ajuste o prompt e gere de novo.</p>
          <button
            type="button"
            onClick={resumeEdit}
            className="mt-3 rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950"
          >
            Editar e gerar novamente
          </button>
        </div>
      ) : null}

      {approved ? (
        <section className="mt-10">
          <p className="label-tech">Character set</p>
          <p className="mt-2 text-sm text-white/45">
            {setComplete
              ? "Poses geradas a partir da imagem aprovada."
              : `Gerando poses… ${setCount} / ${CHARACTER_SET_SIZE}`}
          </p>
          <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {ASSET_ORDER.map((type) => {
              const asset = assetsByType.get(type);
              return (
                <li key={type} className="overflow-hidden rounded-xl border border-white/[0.08] bg-ink-900">
                  {asset ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={asset.image_url} alt={ASSET_LABEL[type]} className="aspect-[2/3] w-full object-cover bg-ink-950" />
                  ) : (
                    <div className="flex aspect-[2/3] items-center justify-center bg-ink-950 text-white/30">
                      <span className="font-mono text-[10px] tracking-wide uppercase">gerando</span>
                    </div>
                  )}
                  <p className="px-3 py-2 font-mono text-[10px] tracking-wide text-white/45 uppercase">
                    {ASSET_LABEL[type]}
                  </p>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {error ? <p className="mt-4 font-mono text-xs text-red-300">{error}</p> : null}
    </div>
  );
}
