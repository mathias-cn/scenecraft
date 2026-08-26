"use client";

import { useEffect, useRef, useState } from "react";

import { advanceProject, generateProjectThumbnail, getProject, uploadProjectThumbnail } from "@/lib/api";
import type { ProjectDetail, Thumbnail } from "@/lib/types";

const POLL_MS = 3000;
const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500 file:mr-3 file:rounded file:border-0 file:bg-brass-500 file:px-2 file:py-1 file:font-mono file:text-[10px] file:tracking-wide file:text-ink-950";

type ThumbnailStagePanelProps = {
  project: ProjectDetail;
  onUpdated: (project: ProjectDetail) => void;
};

function latestOf(thumbs: Thumbnail[], source: string): Thumbnail | undefined {
  const matches = thumbs.filter((item) => item.source === source);
  return matches.at(-1);
}

export function ThumbnailStagePanel({ project, onUpdated }: ThumbnailStagePanelProps) {
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const knownIdsRef = useRef(new Set((project.thumbnails ?? []).map((item) => item.id)));
  const onUpdatedRef = useRef(onUpdated);
  onUpdatedRef.current = onUpdated;

  const thumbs = project.thumbnails ?? [];
  const generated = latestOf(thumbs, "generated");
  const uploaded = latestOf(thumbs, "uploaded");
  const hasThumb = thumbs.length > 0;
  const pending = generating;

  useEffect(() => {
    if (!file) {
      setLocalPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setLocalPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!pending) return undefined;
    const tick = () => {
      if (document.visibilityState === "hidden") return;
      void getProject(project.id)
        .then((next) => {
          const ids = new Set((next.thumbnails ?? []).map((item) => item.id));
          let arrived = false;
          ids.forEach((id) => {
            if (!knownIdsRef.current.has(id)) arrived = true;
          });
          if (arrived) {
            knownIdsRef.current = ids;
            setGenerating(false);
          }
          onUpdatedRef.current(next);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Falha ao atualizar a thumbnail");
        });
    };
    const timer = window.setInterval(tick, POLL_MS);
    return () => window.clearInterval(timer);
  }, [pending, project.id]);

  async function onGenerate() {
    setGenerating(true);
    setError(null);
    knownIdsRef.current = new Set((project.thumbnails ?? []).map((item) => item.id));
    try {
      onUpdated(await generateProjectThumbnail(project.id));
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : "Não foi possível gerar a thumbnail");
    }
  }

  async function onUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const next = await uploadProjectThumbnail(project.id, file);
      knownIdsRef.current = new Set((next.thumbnails ?? []).map((item) => item.id));
      onUpdated(next);
      setFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível enviar a thumbnail");
    } finally {
      setUploading(false);
    }
  }

  async function onApprove() {
    if (!hasThumb) return;
    setBusy(true);
    setError(null);
    try {
      await advanceProject(project.id, "thumbnail_stage");
      onUpdated(await getProject(project.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível avançar");
    } finally {
      setBusy(false);
    }
  }

  const generatedSrc = generated?.file_url ?? null;
  const uploadedSrc = localPreview ?? uploaded?.file_url ?? null;
  const blocked = busy || pending || uploading;

  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        <article className="rounded-lg border border-white/10 bg-ink-950 p-4">
          <p className="label-tech text-brass-500">Gerar com IA</p>
          <p className="mt-2 text-sm text-white/45">
            Resume o vídeo e gera uma thumbnail 16:9 com o provedor de imagem do projeto.
          </p>
          {generatedSrc && !pending ? (
            // eslint-disable-next-line @next/next/no-img-element -- URLs do storage são dinâmicas
            <img src={generatedSrc} alt="Thumbnail gerada" className="mt-4 aspect-video w-full rounded-md object-cover" />
          ) : (
            <div className="mt-4 flex aspect-video items-center justify-center rounded-md bg-white/5 font-mono text-[10px] text-white/25">
              {pending ? "gerando…" : "sem preview"}
            </div>
          )}
          <button
            type="button"
            disabled={blocked}
            onClick={() => void onGenerate()}
            className="mt-4 w-full rounded-md border border-white/15 px-4 py-2.5 text-sm text-white/80 transition hover:border-brass-500 hover:text-brass-400 disabled:opacity-50"
          >
            {pending ? "Gerando…" : generated ? "Regenerar" : "Gerar com IA"}
          </button>
        </article>
        <article className="rounded-lg border border-white/10 bg-ink-950 p-4">
          <p className="label-tech text-brass-500">Fazer upload</p>
          <p className="mt-2 text-sm text-white/45">Envie um PNG, JPG ou WebP. A imagem é salva antes de avançar.</p>
          {uploadedSrc ? (
            // eslint-disable-next-line @next/next/no-img-element -- preview local ou URL do storage
            <img src={uploadedSrc} alt="Thumbnail enviada" className="mt-4 aspect-video w-full rounded-md object-cover" />
          ) : (
            <div className="mt-4 flex aspect-video items-center justify-center rounded-md bg-white/5 font-mono text-[10px] text-white/25">
              sem arquivo
            </div>
          )}
          <label className="label-tech mt-4 block">
            Arquivo de imagem
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={blocked}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className={`${FIELD} disabled:cursor-not-allowed disabled:opacity-50`}
            />
          </label>
          <button
            type="button"
            disabled={blocked || !file}
            onClick={() => void onUpload()}
            className="mt-4 w-full rounded-md border border-white/15 px-4 py-2.5 text-sm text-white/80 transition hover:border-brass-500 hover:text-brass-400 disabled:opacity-50"
          >
            {uploading ? "Enviando…" : "Salvar upload"}
          </button>
        </article>
      </div>
      {error ? <p className="mt-4 font-mono text-xs text-red-300">{error}</p> : null}
      <button
        type="button"
        disabled={blocked || !hasThumb}
        onClick={() => void onApprove()}
        className="mt-5 w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50 sm:w-auto"
      >
        {busy ? "Avançando…" : "Aprovar"}
      </button>
    </div>
  );
}
