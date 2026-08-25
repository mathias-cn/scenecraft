"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { advanceProject, retryProjectStage } from "@/lib/api";
import type { Project } from "@/lib/types";

type ProjectActionsProps = {
  project: Project;
};

export function ProjectActions({ project }: ProjectActionsProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha na ação");
    } finally {
      setBusy(false);
    }
  }

  const showAdvance = project.status === "paused_for_review";
  const showRetry = project.status === "failed";
  if (!showAdvance && !showRetry && !error) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {showAdvance ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void run(() => advanceProject(project.id, project.current_stage))}
          className="rounded-full bg-brass-500 px-3 py-1 font-mono text-[10px] font-medium tracking-wide text-ink-950 uppercase disabled:opacity-50"
        >
          Avançar
        </button>
      ) : null}
      {showRetry ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void run(() => retryProjectStage(project.id))}
          className="rounded-full bg-red-400 px-3 py-1 font-mono text-[10px] font-medium tracking-wide text-ink-950 uppercase disabled:opacity-50"
        >
          Retry estágio
        </button>
      ) : null}
      {error ? <p className="font-mono text-[11px] text-red-300">{error}</p> : null}
    </div>
  );
}
