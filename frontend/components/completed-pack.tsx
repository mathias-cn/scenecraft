"use client";

import { useEffect, useRef, useState } from "react";

import { completeProject, exportProject } from "@/lib/api";
import type { ProjectDetail, ProjectExport } from "@/lib/types";

type CompletedPackProps = {
  project: ProjectDetail;
  onUpdated: (project: ProjectDetail) => void;
};

function needsComplete(stage: string): boolean {
  return stage !== "completed";
}

function latest<T>(items: T[] | undefined): T | undefined {
  if (!items?.length) return undefined;
  return items[items.length - 1];
}

function youtubeTags(tags: string[]): string {
  return tags.filter(Boolean).join(", ");
}

function fileNameFromTitle(title: string): string {
  const slug = title.trim().replace(/[<>:"/\\|?*]+/g, "").replace(/\s+/g, " ").slice(0, 80);
  return `${slug || "video"}.mp4`;
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

async function downloadUrl(url: string, filename: string): Promise<void> {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error("download");
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    clickDownload(objectUrl, filename);
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1500);
  } catch {
    clickDownload(url, filename);
  }
}

function clickDownload(href: string, filename: string): void {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.rel = "noreferrer";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

type CopyBlockProps = {
  label: string;
  value: string;
  multiline?: boolean;
};

function CopyBlock({ label, value, multiline }: CopyBlockProps) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    try {
      await copyText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className="rounded-lg border border-white/10 bg-ink-950 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="label-tech text-brass-500">{label}</p>
        <button
          type="button"
          onClick={() => void onCopy()}
          disabled={!value}
          className="rounded-md border border-white/15 px-3 py-1.5 text-xs text-white/80 transition hover:border-brass-500 hover:text-brass-400 disabled:opacity-40"
        >
          {copied ? "Copiado" : "Copiar"}
        </button>
      </div>
      {multiline ? (
        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-white/75">{value || "—"}</p>
      ) : (
        <p className="mt-3 text-sm text-white/80">{value || "—"}</p>
      )}
    </article>
  );
}

export function CompletedPack({ project, onUpdated }: CompletedPackProps) {
  const [pack, setPack] = useState<ProjectExport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const onUpdatedRef = useRef(onUpdated);
  onUpdatedRef.current = onUpdated;
  const completingRef = useRef(false);

  useEffect(() => {
    if (!needsComplete(project.current_stage) || completingRef.current) return undefined;
    completingRef.current = true;
    void completeProject(project.id)
      .then((next) => onUpdatedRef.current(next))
      .catch((err) => {
        completingRef.current = false;
        setError(err instanceof Error ? err.message : "Não foi possível marcar o projeto como concluído");
      });
    return undefined;
  }, [project.id, project.current_stage]);

  useEffect(() => {
    let cancelled = false;
    void exportProject(project.id)
      .then((next) => {
        if (!cancelled) setPack(next);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Não foi possível carregar o pacote");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  const fallbackThumb = latest(project.thumbnails)?.file_url ?? null;
  const fallbackVideo = project.video_assembly?.output_url ?? null;
  const fallbackDesc = latest(project.descriptions);

  const title = pack?.title || project.title;
  const videoUrl = pack?.video_assembly.output_url ?? fallbackVideo;
  const thumbUrl = pack?.thumbnails.file_url ?? fallbackThumb;
  const description = pack?.descriptions.text ?? fallbackDesc?.text ?? "";
  const tags = pack?.descriptions.tags ?? fallbackDesc?.tags ?? [];
  const tagsLine = youtubeTags(tags);

  async function onDownload() {
    if (!videoUrl) return;
    setDownloading(true);
    setError(null);
    try {
      await downloadUrl(videoUrl, fileNameFromTitle(title));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível baixar o vídeo");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="rounded-xl border border-brass-500/30 bg-ink-900 p-5">
      <p className="label-tech text-brass-500">completed</p>
      <h3 className="mt-2 text-lg font-medium text-white">Pacote pronto</h3>
      <p className="mt-1 mb-5 text-sm text-white/45">
        Baixe o MP4 e copie título, descrição e tags para colar no YouTube Studio.
      </p>
      {videoUrl ? (
        <video controls src={videoUrl} className="aspect-video w-full rounded-lg bg-black" />
      ) : (
        <div className="flex aspect-video items-center justify-center rounded-lg bg-white/5 font-mono text-[10px] text-white/25">
          vídeo indisponível
        </div>
      )}
      <button
        type="button"
        disabled={!videoUrl || downloading}
        onClick={() => void onDownload()}
        className="mt-4 w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50 sm:w-auto"
      >
        {downloading ? "Baixando…" : "Baixar vídeo"}
      </button>
      <div className="mt-6">
        <p className="label-tech text-brass-500">Thumbnail</p>
        {thumbUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- URLs do storage são dinâmicas
          <img src={thumbUrl} alt="Thumbnail" className="mt-3 max-h-64 w-full rounded-lg object-contain" />
        ) : (
          <p className="mt-3 text-sm text-white/40">Nenhuma thumbnail.</p>
        )}
      </div>
      <div className="mt-6 grid gap-3">
        <CopyBlock label="Título" value={title} />
        <CopyBlock label="Descrição" value={description} multiline />
        <CopyBlock label="Tags" value={tagsLine} />
      </div>
      {error ? <p className="mt-4 font-mono text-xs text-red-300">{error}</p> : null}
    </section>
  );
}
