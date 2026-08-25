"use client";

import { FormEvent, useEffect, useState } from "react";

import { createStyle, deleteStyle, listStyles, patchStyle } from "@/lib/api";
import { formatCreatedAt } from "@/lib/project-ui";
import type { Style } from "@/lib/types";

const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

function slugify(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function StylesAdmin() {
  const [styles, setStyles] = useState<Style[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [formOpen, setFormOpen] = useState(false);

  async function refresh() {
    const rows = await listStyles();
    setStyles(rows);
  }

  useEffect(() => {
    void refresh().catch((err) => {
      setError(err instanceof Error ? err.message : "Falha ao listar estilos");
    });
  }, []);

  function onNameChange(next: string) {
    setName(next);
    if (!slugTouched) setSlug(slugify(next));
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || !slug.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await createStyle({ name: name.trim(), slug: slug.trim() });
      setName("");
      setSlug("");
      setSlugTouched(false);
      setFormOpen(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar o estilo");
    } finally {
      setCreating(false);
    }
  }

  async function onToggle(style: Style) {
    setBusyId(style.id);
    setError(null);
    try {
      const updated = await patchStyle(style.id, !style.active);
      setStyles((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível atualizar o estilo");
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(style: Style) {
    if (!window.confirm(`Excluir o estilo “${style.name}”?`)) return;
    setBusyId(style.id);
    setError(null);
    try {
      await deleteStyle(style.id);
      setStyles((current) => current.filter((item) => item.id !== style.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir o estilo");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-white/45">
          Estilos visuais compartilhados por cenas e personagens. Inativos saem dos seletores de
          criação, mas continuam visíveis no histórico.
        </p>
        <button
          type="button"
          onClick={() => setFormOpen((open) => !open)}
          className="rounded-md bg-brass-500 px-3 py-2 text-sm font-medium text-ink-950 transition hover:bg-brass-400"
        >
          Novo estilo
        </button>
      </div>

      {formOpen ? (
        <form
          onSubmit={(event) => void onCreate(event)}
          className="mb-6 rounded-xl border border-white/[0.08] bg-ink-900 p-5"
        >
          <p className="label-tech">Novo estilo</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <label className="label-tech block">
              Nome
              <input
                value={name}
                onChange={(event) => onNameChange(event.target.value)}
                className={FIELD}
                placeholder="Cartoon"
                required
              />
            </label>
            <label className="label-tech block">
              Slug
              <input
                value={slug}
                onChange={(event) => {
                  setSlugTouched(true);
                  setSlug(event.target.value);
                }}
                className={FIELD}
                placeholder="cartoon"
                required
              />
            </label>
          </div>
          <button
            type="submit"
            disabled={creating}
            className="mt-4 rounded-md bg-brass-500 px-4 py-2 text-sm font-medium text-ink-950 disabled:opacity-50"
          >
            {creating ? "Salvando…" : "Criar"}
          </button>
        </form>
      ) : null}

      {error ? (
        <p className="mb-4 rounded-md border border-red-500/30 bg-red-950/40 px-4 py-3 font-mono text-xs text-red-200">
          {error}
        </p>
      ) : null}

      {styles.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 px-4 py-12 text-center text-sm text-white/45">
          Nenhum estilo cadastrado.
        </div>
      ) : (
        <ul className="divide-y divide-white/[0.06] overflow-hidden rounded-xl border border-white/[0.08] bg-ink-900">
          {styles.map((style) => {
            const busy = busyId === style.id;
            return (
              <li key={style.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-white">
                    {style.name}
                    {!style.active ? (
                      <span className="ml-2 rounded-full bg-white/10 px-2 py-0.5 font-mono text-[10px] tracking-wide text-white/45 uppercase">
                        inativo
                      </span>
                    ) : null}
                  </p>
                  <p className="mt-0.5 font-mono text-[11px] text-white/35">
                    {style.slug} · {formatCreatedAt(style.created_at)}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={style.active}
                  disabled={busy}
                  onClick={() => void onToggle(style)}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50 ${
                    style.active ? "bg-brass-500" : "bg-white/15"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-ink-950 transition ${
                      style.active ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void onDelete(style)}
                  className="rounded-md border border-red-500/30 px-2.5 py-1.5 text-xs text-red-300 transition hover:bg-red-950/40 disabled:opacity-50"
                >
                  Excluir
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
