"use client";

import { useState } from "react";

import { advanceProject, getProject, patchTranscript } from "@/lib/api";
import { formatTimecode } from "@/lib/pipeline";
import type { ProjectDetail, TranscriptSegment, TranscriptSegmentPatch } from "@/lib/types";

const FIELD =
  "mt-1 w-full min-h-[4.5rem] resize-y rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

type Draft = {
  id: string;
  index: number;
  start_ms: number;
  text_original: string;
  text_translated: string;
};

type TranscriptReviewProps = {
  project: ProjectDetail;
  onUpdated: (project: ProjectDetail) => void;
};

function toDrafts(segments: TranscriptSegment[]): Draft[] {
  return segments.map((segment) => ({
    id: segment.id,
    index: segment.index,
    start_ms: segment.start_ms,
    text_original: segment.text_original,
    text_translated: segment.text_translated ?? "",
  }));
}

function changedPatches(segments: TranscriptSegment[], drafts: Draft[]): TranscriptSegmentPatch[] {
  const byId = new Map(segments.map((segment) => [segment.id, segment]));
  const patches: TranscriptSegmentPatch[] = [];
  for (const draft of drafts) {
    const current = byId.get(draft.id);
    if (!current) continue;
    const original = draft.text_original;
    const translated = draft.text_translated.trim() ? draft.text_translated : null;
    const originalChanged = original !== current.text_original;
    const translatedChanged = translated !== current.text_translated;
    if (!originalChanged && !translatedChanged) continue;
    const patch: TranscriptSegmentPatch = { id: draft.id };
    if (originalChanged) patch.text_original = original;
    if (translatedChanged) patch.text_translated = translated;
    patches.push(patch);
  }
  return patches;
}

export function TranscriptReview({ project, onUpdated }: TranscriptReviewProps) {
  const [drafts, setDrafts] = useState(() => toDrafts(project.transcript_segments));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateDraft(id: string, field: "text_original" | "text_translated", value: string) {
    setDrafts((prev) => prev.map((draft) => (draft.id === id ? { ...draft, [field]: value } : draft)));
  }

  async function onApprove() {
    const empty = drafts.find((draft) => !draft.text_original.trim());
    if (empty) {
      setError("O texto original não pode ficar vazio.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const patches = changedPatches(project.transcript_segments, drafts);
      if (patches.length > 0) {
        await patchTranscript(project.id, patches);
      }
      await advanceProject(project.id, "transcript_review");
      onUpdated(await getProject(project.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível aprovar o transcript");
    } finally {
      setBusy(false);
    }
  }

  if (drafts.length === 0) {
    return <p className="text-sm text-white/40">Nenhum segmento de transcript ainda.</p>;
  }

  return (
    <div>
      <ul className="max-h-[28rem] space-y-4 overflow-y-auto pr-1">
        {drafts.map((draft) => (
          <li key={draft.id} className="rounded-lg border border-white/10 bg-ink-950/60 p-3">
            <p className="font-mono text-[10px] text-white/35">
              {formatTimecode(draft.start_ms)}
              <span className="ml-2 text-white/20">#{draft.index}</span>
            </p>
            <div className="mt-2 grid gap-3 md:grid-cols-2">
              <label className="block">
                <span className="label-tech text-white/40">Original</span>
                <textarea
                  value={draft.text_original}
                  onChange={(event) => updateDraft(draft.id, "text_original", event.target.value)}
                  className={FIELD}
                  rows={3}
                />
              </label>
              <label className="block">
                <span className="label-tech text-brass-500/80">Traduzido</span>
                <textarea
                  value={draft.text_translated}
                  onChange={(event) => updateDraft(draft.id, "text_translated", event.target.value)}
                  className={FIELD}
                  rows={3}
                />
              </label>
            </div>
          </li>
        ))}
      </ul>
      {error ? <p className="mt-4 font-mono text-xs text-red-300">{error}</p> : null}
      <button
        type="button"
        disabled={busy}
        onClick={() => void onApprove()}
        className="mt-5 w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50 sm:w-auto"
      >
        {busy ? "Salvando…" : "Aprovar transcript"}
      </button>
    </div>
  );
}
