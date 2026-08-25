"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { advanceProject, createProject, getProject, listProjects, retryProjectStage } from "@/lib/api";
import type { Project, ProjectDetail, ProjectStage, ProjectStatus, SourceType } from "@/lib/types";

const STAGES: ProjectStage[] = [
  "created",
  "transcribing",
  "transcript_review",
  "scene_planning",
  "scene_review",
  "generating_media",
  "media_review",
  "audio_stage",
  "audio_review",
  "rendering",
  "render_review",
  "thumbnail_stage",
  "description_stage",
  "ready_to_publish",
  "uploading",
  "published",
];

const STAGE_LABEL: Record<ProjectStage, string> = {
  created: "Criado",
  transcribing: "Transcrição",
  transcript_review: "Review transcrição",
  scene_planning: "Cenas",
  scene_review: "Review cenas",
  generating_media: "Mídia",
  media_review: "Review mídia",
  audio_stage: "Áudio",
  audio_review: "Review áudio",
  rendering: "Render",
  render_review: "Review render",
  thumbnail_stage: "Thumb",
  description_stage: "Descrição",
  ready_to_publish: "Pronto p/ publicar",
  uploading: "Upload",
  published: "Publicado",
  failed: "Falhou",
};

const SOURCE_LABEL: Record<SourceType, string> = {
  youtube_link: "Link do YouTube",
  upload_video: "Upload de vídeo",
  upload_audio: "Upload de áudio",
};

function isActive(status: ProjectStatus) {
  return status === "pending" || status === "running";
}

export default function HomePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("youtube_link");
  const [sourceRef, setSourceRef] = useState("");
  const [targetLanguage, setTargetLanguage] = useState("pt-BR");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const needsFile = sourceType !== "youtube_link";

  const refresh = useCallback(async () => {
    try {
      const data = await listProjects();
      setProjects(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao falar com a API");
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    if (needsFile && !file) {
      setError("Selecione um arquivo de vídeo ou áudio.");
      return;
    }
    if (!needsFile && !sourceRef.trim()) return;
    setBusy(true);
    try {
      await createProject(
        {
          title: title.trim(),
          source_type: sourceType,
          source_ref: needsFile ? undefined : sourceRef.trim(),
          target_language: targetLanguage.trim() || "pt-BR",
          automation_config: {},
        },
        file,
      );
      setTitle("");
      setSourceRef("");
      setFile(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar o projeto");
    } finally {
      setBusy(false);
    }
  }

  async function onAdvance(project: Project) {
    setBusy(true);
    try {
      await advanceProject(project.id, project.current_stage);
      await refresh();
      if (openId === project.id) {
        setDetail(await getProject(project.id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível avançar o estágio");
    } finally {
      setBusy(false);
    }
  }

  async function onRetry(project: Project) {
    setBusy(true);
    try {
      await retryProjectStage(project.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível reexecutar o estágio");
    } finally {
      setBusy(false);
    }
  }

  async function onToggleDetail(project: Project) {
    if (openId === project.id) {
      setOpenId(null);
      setDetail(null);
      return;
    }
    try {
      const data = await getProject(project.id);
      setOpenId(project.id);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar o detalhe");
    }
  }

  const inFlight = useMemo(
    () => projects.filter((project) => isActive(project.status)).length,
    [projects],
  );

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-6 py-12">
      <header className="mb-12 flex flex-col gap-4 border-b border-white/10 pb-8 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs tracking-[0.35em] text-brass-500 uppercase">YouTube · pipeline</p>
          <h1 className="font-display text-4xl font-semibold tracking-tight text-brass-400 sm:text-5xl">
            SceneCraft
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-white/55">
            Da fonte ao upload: transcrição, cenas, áudio, montagem e publicação.
          </p>
        </div>
        <div className="text-right text-xs text-white/40">
          <div>
            {projects.length} projeto{projects.length === 1 ? "" : "s"}
          </div>
          <div className="text-brass-500">{inFlight} em produção</div>
        </div>
      </header>

      <section className="mb-12 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <form
          onSubmit={onSubmit}
          className="rounded-2xl border border-white/10 bg-ink-800/80 p-6 shadow-[0_20px_60px_rgba(0,0,0,0.35)]"
        >
          <h2 className="font-display text-xl text-brass-400">Novo projeto</h2>
          <label className="mt-5 block text-xs tracking-widest text-white/45 uppercase">
            Título
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="mt-2 w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-white outline-none focus:border-brass-500"
              placeholder="Como eu automatizei meu canal"
              required
            />
          </label>
          <label className="mt-4 block text-xs tracking-widest text-white/45 uppercase">
            Fonte
            <select
              value={sourceType}
              onChange={(event) => {
                setSourceType(event.target.value as SourceType);
                setFile(null);
              }}
              className="mt-2 w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-white outline-none focus:border-brass-500"
            >
              <option value="youtube_link">Link do YouTube</option>
              <option value="upload_video">Upload de vídeo</option>
              <option value="upload_audio">Upload de áudio</option>
            </select>
          </label>
          {needsFile ? (
            <label className="mt-4 block text-xs tracking-widest text-white/45 uppercase">
              Arquivo
              <input
                type="file"
                accept={sourceType === "upload_audio" ? "audio/*" : "video/*"}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="mt-2 w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-white outline-none file:mr-3 file:rounded file:border-0 file:bg-brass-500 file:px-2 file:py-1 file:text-ink-950 focus:border-brass-500"
                required
              />
            </label>
          ) : (
            <label className="mt-4 block text-xs tracking-widest text-white/45 uppercase">
              Link do YouTube
              <textarea
                value={sourceRef}
                onChange={(event) => setSourceRef(event.target.value)}
                rows={3}
                className="mt-2 w-full resize-y rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm leading-relaxed text-white outline-none focus:border-brass-500"
                placeholder="https://www.youtube.com/watch?v=…"
                required
              />
            </label>
          )}
          <label className="mt-4 block text-xs tracking-widest text-white/45 uppercase">
            Idioma alvo
            <input
              value={targetLanguage}
              onChange={(event) => setTargetLanguage(event.target.value)}
              className="mt-2 w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-white outline-none focus:border-brass-500"
              placeholder="pt-BR"
              required
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="mt-5 w-full rounded-lg bg-brass-500 px-4 py-2.5 text-sm font-semibold text-ink-950 transition hover:bg-brass-400 disabled:opacity-50"
          >
            {busy ? "Enfileirando…" : "Gerar vídeo"}
          </button>
        </form>

        <aside className="self-start rounded-2xl border border-dashed border-white/10 p-6 text-sm text-white/50">
          <p className="text-xs tracking-widest text-brass-500 uppercase">Pipeline</p>
          <ol className="mt-4 space-y-3">
            <li>1. Ingestão da fonte</li>
            <li>2. Transcrição e tradução</li>
            <li>3. Cenas visuais + áudio</li>
            <li>4. Montagem FFmpeg</li>
            <li>5. Thumb, descrição e YouTube</li>
          </ol>
          <p className="mt-6 text-xs leading-relaxed text-white/35">
            O schema vive em Postgres (Alembic). Sem chaves no <code className="text-white/55">.env</code>, o
            worker avança os estágios em modo stub.
          </p>
        </aside>
      </section>

      {error && (
        <p className="mb-6 rounded-lg border border-red-500/30 bg-red-950/40 px-4 py-3 text-sm text-red-200">
          {error}
        </p>
      )}

      <section>
        <h2 className="mb-4 font-display text-xl text-brass-400">Fila</h2>
        {!ready ? (
          <p className="text-sm text-white/40">Carregando…</p>
        ) : projects.length === 0 ? (
          <p className="text-sm text-white/40">Nenhum projeto ainda. Envie uma fonte para começar.</p>
        ) : (
          <ul className="space-y-4">
            {projects.map((project) => (
              <li key={project.id} className="rounded-2xl border border-white/10 bg-ink-800/60 p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-display text-lg text-white">{project.title}</h3>
                    <p className="mt-1 max-w-2xl text-sm text-white/45">
                      {SOURCE_LABEL[project.source_type]} · {project.status} · {project.source_ref}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {project.status === "paused_for_review" && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onAdvance(project)}
                        className="rounded-full bg-brass-500 px-3 py-1 text-xs font-semibold text-ink-950 disabled:opacity-50"
                      >
                        Avançar
                      </button>
                    )}
                    {project.status === "failed" && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onRetry(project)}
                        className="rounded-full bg-red-400 px-3 py-1 text-xs font-semibold text-ink-950 disabled:opacity-50"
                      >
                        Retry estágio
                      </button>
                    )}
                  <span
                    className={`rounded-full px-3 py-1 text-xs tracking-wide uppercase ${
                      project.status === "failed"
                        ? "bg-red-500/20 text-red-300"
                        : project.status === "completed" || project.current_stage === "published"
                          ? "bg-brass-500/20 text-brass-400"
                          : project.status === "paused_for_review"
                            ? "bg-white/10 text-brass-400"
                            : "bg-white/10 text-white/70"
                    }`}
                  >
                    {STAGE_LABEL[project.current_stage]}
                  </span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => void onToggleDetail(project)}
                  className="mt-3 text-xs tracking-widest text-brass-500 uppercase"
                >
                  {openId === project.id ? "Ocultar detalhe" : "Ver cenas, áudio e montagem"}
                </button>
                {openId === project.id && detail && detail.id === project.id && (
                  <div className="mt-3 space-y-2 rounded-xl border border-white/10 bg-ink-950/50 p-4 text-sm text-white/60">
                    <p>{detail.scenes.length} cena(s)</p>
                    <p>{detail.audio_tracks.length} faixa(s) de áudio</p>
                    <p>
                      Montagem:{" "}
                      {detail.video_assembly
                        ? `${detail.video_assembly.status}${detail.video_assembly.output_url ? ` · ${detail.video_assembly.output_url}` : ""}`
                        : "ainda não renderizada"}
                    </p>
                    {detail.scenes.slice(0, 5).map((scene) => (
                      <p key={scene.id} className="text-xs text-white/40">
                        #{scene.index} {scene.visual_prompt}
                      </p>
                    ))}
                  </div>
                )}
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {STAGES.map((stage) => {
                    const currentIndex = STAGES.indexOf(project.current_stage);
                    const stageIndex = STAGES.indexOf(stage);
                    const done =
                      project.status === "completed" ||
                      project.current_stage === "published" ||
                      stageIndex <= currentIndex;
                    return (
                      <span
                        key={stage}
                        className={`rounded-full px-2.5 py-1 text-[10px] tracking-wider uppercase ${
                          done ? "bg-brass-500/20 text-brass-400" : "bg-white/5 text-white/30"
                        }`}
                      >
                        {STAGE_LABEL[stage]}
                      </span>
                    );
                  })}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
