"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { StyleSelect } from "@/components/style-select";
import { createProject } from "@/lib/api";
import {
  AUTOMATION_TOGGLES,
  IMAGE_PROVIDERS,
  SOURCE_OPTIONS,
  TRANSCRIPT_LANGUAGES,
  defaultAutomation,
  toAutomationPayload,
  type AutomationConfig,
  type ImageProviderName,
  type TranscriptLanguage,
} from "@/lib/project-form";
import type { SourceType } from "@/lib/types";

const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

type ToggleRowProps = {
  label: string;
  pause: string;
  checked: boolean;
  onChange: (next: boolean) => void;
};

function ToggleRow({ label, pause, checked, onChange }: ToggleRowProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div className="min-w-0">
        <p className="text-sm text-white/90">{label}</p>
        <p className="mt-0.5 font-mono text-[10px] tracking-wide text-white/35">
          {checked ? "segue sem pausa" : `pausa em ${pause}`}
        </p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition ${
          checked ? "bg-brass-500" : "bg-white/15"
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-ink-950 transition ${
            checked ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}

export function ProjectCreateForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("youtube_link");
  const [sourceRef, setSourceRef] = useState("");
  const [language, setLanguage] = useState<TranscriptLanguage>("original");
  const [imageProvider, setImageProvider] = useState<ImageProviderName>("higgsfield");
  const [sceneStyle, setSceneStyle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [automation, setAutomation] = useState<AutomationConfig>(defaultAutomation);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const needsFile = sourceType !== "youtube_link";

  function setSource(next: SourceType) {
    setSourceType(next);
    setFile(null);
    if (next !== "youtube_link") setSourceRef("");
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    if (needsFile && !file) {
      setError("Selecione um arquivo de vídeo ou áudio.");
      return;
    }
    if (!needsFile && !sourceRef.trim()) {
      setError("Informe o link do YouTube.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const project = await createProject(
        {
          title: title.trim(),
          source_type: sourceType,
          source_ref: needsFile ? undefined : sourceRef.trim(),
          target_language: language,
          automation_config: toAutomationPayload(automation, imageProvider, sceneStyle),
          image_provider: imageProvider,
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
    <form onSubmit={onSubmit} className="space-y-8">
      <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
        <p className="label-tech">Projeto</p>
        <label className="label-tech mt-4 block">
          Título
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className={FIELD}
            placeholder="Como eu automatizei meu canal"
            required
          />
        </label>
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
        <p className="label-tech">Origem</p>
        <div role="tablist" aria-label="Origem do projeto" className="mt-3 grid grid-cols-3 gap-1 rounded-lg bg-ink-950 p-1">
          {SOURCE_OPTIONS.map((option) => {
            const active = sourceType === option.value;
            return (
              <button
                key={option.value}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setSource(option.value)}
                className={`rounded-md px-2 py-2 text-center text-xs transition sm:text-sm ${
                  active ? "bg-brass-500 font-medium text-ink-950" : "text-white/50 hover:text-white/80"
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
        <p className="mt-2 font-mono text-[10px] text-white/30">
          {SOURCE_OPTIONS.find((option) => option.value === sourceType)?.hint}
        </p>

        {needsFile ? (
          <label className="label-tech mt-4 block">
            Arquivo
            <input
              type="file"
              accept={sourceType === "upload_audio" ? "audio/*" : "video/*"}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className={`${FIELD} file:mr-3 file:rounded file:border-0 file:bg-brass-500 file:px-2 file:py-1 file:font-mono file:text-[10px] file:tracking-wide file:text-ink-950`}
              required
            />
          </label>
        ) : (
          <label className="label-tech mt-4 block">
            Link do YouTube
            <input
              type="text"
              value={sourceRef}
              onChange={(event) => setSourceRef(event.target.value)}
              className={FIELD}
              placeholder="https://www.youtube.com/watch?v=…"
              required
            />
          </label>
        )}
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
        <p className="label-tech">Idioma da transcrição</p>
        <fieldset className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <legend className="sr-only">Idioma da transcrição</legend>
          {TRANSCRIPT_LANGUAGES.map((option) => {
            const active = language === option.value;
            return (
              <label
                key={option.value}
                className={`cursor-pointer rounded-md border px-3 py-2 text-center text-sm transition ${
                  active
                    ? "border-brass-500 bg-brass-500/10 text-brass-400"
                    : "border-white/10 text-white/55 hover:border-white/20"
                }`}
              >
                <input
                  type="radio"
                  name="transcript_language"
                  value={option.value}
                  checked={active}
                  onChange={() => setLanguage(option.value)}
                  className="sr-only"
                />
                {option.label}
              </label>
            );
          })}
        </fieldset>
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
        <StyleSelect value={sceneStyle} onChange={setSceneStyle} />
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
        <p className="label-tech">Provider de imagem</p>
        <fieldset className="mt-3 grid grid-cols-2 gap-2">
          <legend className="sr-only">Provider de imagem</legend>
          {IMAGE_PROVIDERS.map((option) => {
            const active = imageProvider === option.value;
            return (
              <label
                key={option.value}
                className={`cursor-pointer rounded-md border px-3 py-2 text-center text-sm transition ${
                  active
                    ? "border-brass-500 bg-brass-500/10 text-brass-400"
                    : "border-white/10 text-white/55 hover:border-white/20"
                }`}
              >
                <input
                  type="radio"
                  name="image_provider"
                  value={option.value}
                  checked={active}
                  onChange={() => setImageProvider(option.value)}
                  className="sr-only"
                />
                {option.label}
              </label>
            );
          })}
        </fieldset>
        <p className="mt-2 font-mono text-[10px] text-white/30">
          {IMAGE_PROVIDERS.find((option) => option.value === imageProvider)?.hint}
        </p>
      </section>

      <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
        <p className="label-tech">Automação</p>
        <p className="mt-2 text-sm text-white/45">
          Toggle ligado: a etapa segue sozinha. Desligado: o pipeline pausa naquele estágio para
          revisão manual.
        </p>
        <div className="mt-2 divide-y divide-white/[0.06]">
          {AUTOMATION_TOGGLES.map((item) => (
            <ToggleRow
              key={item.key}
              label={item.label}
              pause={item.pause}
              checked={automation[item.key]}
              onChange={(next) => setAutomation((current) => ({ ...current, [item.key]: next }))}
            />
          ))}
        </div>
      </section>

      {error ? (
        <p className="rounded-md border border-red-500/30 bg-red-950/40 px-4 py-3 font-mono text-xs text-red-200">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={busy}
        className="w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50"
      >
        {busy ? "Criando…" : "Criar projeto"}
      </button>
    </form>
  );
}
