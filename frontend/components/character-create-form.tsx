"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { StyleSelect } from "@/components/style-select";
import { createCharacter, retryCharacter } from "@/lib/api";
import { clearCharacterDraft, readCharacterDraft } from "@/lib/character-draft";

const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

export function CharacterCreateForm() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [styleId, setStyleId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [referenceUrl, setReferenceUrl] = useState<string | null>(null);
  const [retryId, setRetryId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const draft = readCharacterDraft();
    if (!draft) return;
    setPrompt(draft.description_prompt);
    setStyleId(draft.style_id);
    setReferenceUrl(draft.reference_image_url ?? null);
    setRetryId(draft.characterId ?? null);
    clearCharacterDraft();
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim() || !styleId) return;
    setBusy(true);
    setError(null);
    const payload = {
      description_prompt: prompt.trim(),
      style_id: styleId,
      reference_image_url: file ? undefined : referenceUrl,
    };
    try {
      const character = retryId
        ? await retryCharacter(retryId, payload, file)
        : await createCharacter(payload, file);
      router.push(`/characters/${character.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar o personagem");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-8">
      <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
        <label className="label-tech block">
          Descrição
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            className={`${FIELD} min-h-32 resize-y`}
            placeholder="Mulher de 30 anos, cabelo cacheado, casaco vermelho, expressão serena…"
            required
          />
        </label>
        <p className="mt-2 font-mono text-[10px] text-white/30">
          Quanto mais concreto (idade, roupa, traços), mais consistente fica a imagem base.
        </p>
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
        <StyleSelect
          value={styleId}
          onChange={setStyleId}
          valueKind="id"
          includeSlug={styleId}
          hint="Somente estilos ativos. O estilo já usado em um personagem continua visível mesmo inativo."
        />
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
        <p className="label-tech">Imagem de referência</p>
        <p className="mt-2 text-sm text-white/45">Opcional. Se enviar, a geração parte desta foto em vez de criar do zero.</p>
        {referenceUrl && !file ? (
          <p className="mt-3 font-mono text-[11px] text-white/40">
            Referência anterior mantida. Envie outro arquivo para substituir.
          </p>
        ) : null}
        <label className="label-tech mt-4 block">
          Upload (opcional)
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className={`${FIELD} file:mr-3 file:rounded file:border-0 file:bg-brass-500 file:px-2 file:py-1 file:font-mono file:text-[10px] file:tracking-wide file:text-ink-950`}
          />
        </label>
      </section>

      {error ? (
        <p className="rounded-md border border-red-500/30 bg-red-950/40 px-4 py-3 font-mono text-xs text-red-200">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={busy || !styleId}
        className="w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50"
      >
        {busy ? "Enviando…" : retryId ? "Gerar novamente" : "Gerar imagem base"}
      </button>
    </form>
  );
}
