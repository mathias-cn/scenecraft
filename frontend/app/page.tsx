"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { createJob, listJobs } from "@/lib/api";
import type { Job, JobStatus } from "@/lib/types";

const STAGES: JobStatus[] = [
  "pending",
  "scripting",
  "voicing",
  "generating",
  "uploading",
  "completed",
];

const STAGE_LABEL: Record<JobStatus, string> = {
  pending: "Fila",
  scripting: "Roteiro",
  voicing: "Narração",
  generating: "Vídeo",
  uploading: "YouTube",
  completed: "Pronto",
  failed: "Falhou",
};

function isActive(status: JobStatus) {
  return status !== "completed" && status !== "failed";
}

export default function HomePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await listJobs();
      setJobs(data);
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
    if (!title.trim() || !prompt.trim()) return;
    setBusy(true);
    try {
      await createJob({ title: title.trim(), prompt: prompt.trim() });
      setTitle("");
      setPrompt("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar o job");
    } finally {
      setBusy(false);
    }
  }

  const inFlight = useMemo(() => jobs.filter((job) => isActive(job.status)).length, [jobs]);

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-6 py-12">
      <header className="mb-12 flex flex-col gap-4 border-b border-white/10 pb-8 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs tracking-[0.35em] text-brass-500 uppercase">YouTube · pipeline</p>
          <h1 className="font-display text-4xl font-semibold tracking-tight text-brass-400 sm:text-5xl">
            SceneCraft
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-white/55">
            Da ideia ao upload: roteiro, voz, vídeo e publicação — enfileirado no Celery.
          </p>
        </div>
        <div className="text-right text-xs text-white/40">
          <div>{jobs.length} job{jobs.length === 1 ? "" : "s"}</div>
          <div className="text-brass-500">{inFlight} em produção</div>
        </div>
      </header>

      <section className="mb-12 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <form
          onSubmit={onSubmit}
          className="rounded-2xl border border-white/10 bg-ink-800/80 p-6 shadow-[0_20px_60px_rgba(0,0,0,0.35)]"
        >
          <h2 className="font-display text-xl text-brass-400">Nova cena</h2>
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
            Ideia / briefing
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              rows={6}
              className="mt-2 w-full resize-y rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm leading-relaxed text-white outline-none focus:border-brass-500"
              placeholder="Explique o vídeo em algumas frases. O worker gera roteiro, narração e clip."
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
            <li>1. Anthropic escreve o roteiro</li>
            <li>2. ElevenLabs gera a narração</li>
            <li>3. Higgsfield produz o vídeo</li>
            <li>4. S3 / R2 guarda o arquivo</li>
            <li>5. YouTube recebe o upload</li>
          </ol>
          <p className="mt-6 text-xs leading-relaxed text-white/35">
            Sem chaves no <code className="text-white/55">.env</code>, o worker corre em modo stub para
            você validar o stack com <code className="text-white/55">docker compose up</code>.
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
        ) : jobs.length === 0 ? (
          <p className="text-sm text-white/40">Nenhum job ainda. Envie uma ideia para começar.</p>
        ) : (
          <ul className="space-y-4">
            {jobs.map((job) => (
              <li
                key={job.id}
                className="rounded-2xl border border-white/10 bg-ink-800/60 p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-display text-lg text-white">{job.title}</h3>
                    <p className="mt-1 max-w-2xl text-sm text-white/45">{job.prompt}</p>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-xs tracking-wide uppercase ${
                      job.status === "failed"
                        ? "bg-red-500/20 text-red-300"
                        : job.status === "completed"
                          ? "bg-brass-500/20 text-brass-400"
                          : "bg-white/10 text-white/70"
                    }`}
                  >
                    {STAGE_LABEL[job.status]}
                  </span>
                </div>
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {STAGES.map((stage) => {
                    const currentIndex = STAGES.indexOf(
                      job.status === "failed" ? "pending" : job.status,
                    );
                    const stageIndex = STAGES.indexOf(stage);
                    const done = job.status === "completed" || stageIndex <= currentIndex;
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
                {job.youtube_url && (
                  <a
                    href={job.youtube_url}
                    className="mt-3 inline-block text-sm text-brass-400 underline-offset-4 hover:underline"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {job.youtube_url}
                  </a>
                )}
                {job.error && <p className="mt-3 text-sm text-red-300">{job.error}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
