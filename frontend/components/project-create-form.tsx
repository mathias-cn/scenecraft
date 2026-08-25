"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { createProject } from "@/lib/api";
import type { SourceType } from "@/lib/types";

const INPUT =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

export function ProjectCreateForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("youtube_link");
  const [sourceRef, setSourceRef] = useState("");
  const [targetLanguage, setTargetLanguage] = useState("pt-BR");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const needsFile = sourceType !== "youtube_link";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    if (needsFile && !file) {
      setError("Selecione um arquivo de vídeo ou áudio.");
      return;
    }
    if (!needsFile && !sourceRef.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const project = await createProject(
        {
          title: title.trim(),
          source_type: sourceType,
          source_ref: needsFile ? undefined : sourceRef.trim(),
          target_language: targetLanguage.trim() || "pt-BR",
          automation_config: {},
        },
        file,
      );
      router.push(`/projects/${project.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar o projeto");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
      <label className="label-tech block">
        Título
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className={INPUT}
          placeholder="Como eu automatizei meu canal"
          required
        />
      </label>
      <label className="label-tech mt-4 block">
        Fonte
        <select
          value={sourceType}
          onChange={(event) => {
            setSourceType(event.target.value as SourceType);
            setFile(null);
          }}
          className={INPUT}
        >
          <option value="youtube_link">Link do YouTube</option>
          <option value="upload_video">Upload de vídeo</option>
          <option value="upload_audio">Upload de áudio</option>
        </select>
      </label>
      {needsFile ? (
        <label className="label-tech mt-4 block">
          Arquivo
          <input
            type="file"
            accept={sourceType === "upload_audio" ? "audio/*" : "video/*"}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className={`${INPUT} file:mr-3 file:rounded file:border-0 file:bg-brass-500 file:px-2 file:py-1 file:font-mono file:text-[10px] file:tracking-wide file:text-ink-950`}
            required
          />
        </label>
      ) : (
        <label className="label-tech mt-4 block">
          Link do YouTube
          <textarea
            value={sourceRef}
            onChange={(event) => setSourceRef(event.target.value)}
            rows={3}
            className={`${INPUT} resize-y`}
            placeholder="https://www.youtube.com/watch?v=…"
            required
          />
        </label>
      )}
      <label className="label-tech mt-4 block">
        Idioma alvo
        <input
          value={targetLanguage}
          onChange={(event) => setTargetLanguage(event.target.value)}
          className={`${INPUT} font-mono`}
          placeholder="pt-BR"
          required
        />
      </label>
      {error ? (
        <p className="mt-4 rounded-md border border-red-500/30 bg-red-950/40 px-3 py-2 font-mono text-xs text-red-200">
          {error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={busy}
        className="mt-5 w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50"
      >
        {busy ? "Enfileirando…" : "Criar projeto"}
      </button>
    </form>
  );
}
