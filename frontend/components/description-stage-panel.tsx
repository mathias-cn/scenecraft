"use client";

import { useEffect, useRef, useState } from "react";

import { confirmProjectDescription, generateProjectDescription, getProject } from "@/lib/api";
import type { Description, ProjectDetail } from "@/lib/types";

const POLL_MS = 3000;
const MAX_TAGS = 15;
const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500 disabled:cursor-not-allowed disabled:opacity-50";

type DescriptionStagePanelProps = {
  project: ProjectDetail;
  onUpdated: (project: ProjectDetail) => void;
};

function latestDescription(items: Description[] | undefined): Description | undefined {
  if (!items?.length) return undefined;
  return items[items.length - 1];
}

function sanitizeTag(raw: string): string {
  return raw.replaceAll(",", " ").replace(/^#+/, "").trim().replace(/\s+/g, " ");
}

function hasTag(tags: string[], candidate: string): boolean {
  const key = candidate.toLocaleLowerCase();
  return tags.some((tag) => tag.toLocaleLowerCase() === key);
}

type TagChipsProps = {
  tags: string[];
  disabled: boolean;
  onRemove: (tag: string) => void;
};

function TagChips({ tags, disabled, onRemove }: TagChipsProps) {
  if (tags.length === 0) {
    return <p className="mt-2 text-sm text-white/40">Nenhuma tag ainda.</p>;
  }
  return (
    <ul className="mt-2 flex flex-wrap gap-2">
      {tags.map((tag) => (
        <li
          key={tag.toLocaleLowerCase()}
          className="flex items-center gap-1 rounded-full border border-white/15 bg-ink-950 py-1 pr-1 pl-3 text-sm text-white/80"
        >
          <span>{tag}</span>
          <button
            type="button"
            disabled={disabled}
            aria-label={`Remover tag ${tag}`}
            onClick={() => onRemove(tag)}
            className="flex h-6 w-6 items-center justify-center rounded-full text-white/45 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}

export function DescriptionStagePanel({ project, onUpdated }: DescriptionStagePanelProps) {
  const latest = latestDescription(project.descriptions);
  const latestId = latest?.id ?? "";
  const [text, setText] = useState(latest?.text ?? "");
  const [tags, setTags] = useState<string[]>(latest?.tags ?? []);
  const [draftTag, setDraftTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const knownIdsRef = useRef(new Set((project.descriptions ?? []).map((item) => item.id)));
  const onUpdatedRef = useRef(onUpdated);
  onUpdatedRef.current = onUpdated;

  useEffect(() => {
    setText(latest?.text ?? "");
    setTags(latest?.tags ?? []);
    // latestId is the sync key so local edits survive project refreshes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestId]);

  const pending = generating;

  useEffect(() => {
    if (!pending) return undefined;
    const tick = () => {
      if (document.visibilityState === "hidden") return;
      void getProject(project.id)
        .then((next) => {
          const ids = new Set((next.descriptions ?? []).map((item) => item.id));
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
          setError(err instanceof Error ? err.message : "Falha ao atualizar a descrição");
        });
    };
    const timer = window.setInterval(tick, POLL_MS);
    return () => window.clearInterval(timer);
  }, [pending, project.id]);

  const blocked = busy || pending;
  const canConfirm = Boolean(text.trim()) && !blocked;

  function addDraftTag() {
    const parts = draftTag.split(",").map(sanitizeTag).filter(Boolean);
    if (parts.length === 0) {
      setDraftTag("");
      return;
    }
    setTags((current) => {
      const next = [...current];
      for (const part of parts) {
        if (next.length >= MAX_TAGS || hasTag(next, part)) continue;
        next.push(part);
      }
      return next;
    });
    setDraftTag("");
  }

  async function onRegenerate() {
    setGenerating(true);
    setError(null);
    knownIdsRef.current = new Set((project.descriptions ?? []).map((item) => item.id));
    try {
      onUpdated(await generateProjectDescription(project.id));
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : "Não foi possível regenerar a descrição");
    }
  }

  async function onConfirm() {
    const body = text.trim();
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      onUpdated(await confirmProjectDescription(project.id, { text: body, tags }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível confirmar a descrição");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <label className="label-tech block">
        Descrição
        <textarea
          value={text}
          disabled={blocked}
          rows={6}
          onChange={(event) => setText(event.target.value)}
          placeholder="Resumo do vídeo e um call-to-action, se fizer sentido."
          className={`${FIELD} min-h-[9rem] resize-y`}
        />
      </label>
      <div className="mt-5">
        <p className="label-tech">Tags do YouTube</p>
        <p className="mt-1 text-sm text-white/45">
          10 a 15 palavras-chave, sem hashtag. Espaços são permitidos; vírgula adiciona a tag.
        </p>
        <TagChips
          tags={tags}
          disabled={blocked}
          onRemove={(tag) => setTags((current) => current.filter((item) => item !== tag))}
        />
        {tags.length < MAX_TAGS ? (
          <div className="mt-3 flex gap-2">
            <input
              type="text"
              value={draftTag}
              disabled={blocked}
              placeholder="Nova tag"
              onChange={(event) => setDraftTag(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === ",") {
                  event.preventDefault();
                  addDraftTag();
                }
              }}
              className={`${FIELD} mt-0`}
            />
            <button
              type="button"
              disabled={blocked || !sanitizeTag(draftTag)}
              onClick={addDraftTag}
              className="shrink-0 rounded-md border border-white/15 px-3 text-sm text-white/80 transition hover:border-brass-500 hover:text-brass-400 disabled:opacity-50"
            >
              Adicionar
            </button>
          </div>
        ) : (
          <p className="mt-3 font-mono text-[10px] text-white/35">Limite de {MAX_TAGS} tags.</p>
        )}
      </div>
      {error ? <p className="mt-4 font-mono text-xs text-red-300">{error}</p> : null}
      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          disabled={blocked}
          onClick={() => void onRegenerate()}
          className="rounded-md border border-white/15 px-4 py-2.5 text-sm text-white/80 transition hover:border-brass-500 hover:text-brass-400 disabled:opacity-50"
        >
          {pending ? "Gerando…" : "Regenerar"}
        </button>
        <button
          type="button"
          disabled={!canConfirm}
          onClick={() => void onConfirm()}
          className="rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50"
        >
          {busy ? "Salvando…" : "Confirmar"}
        </button>
      </div>
    </div>
  );
}
