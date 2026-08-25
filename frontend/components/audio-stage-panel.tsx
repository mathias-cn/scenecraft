"use client";

import { useEffect, useState } from "react";

import { generateProjectAudio, listAudioVoices, uploadProjectAudio } from "@/lib/api";
import { audioGenerationModeOf } from "@/lib/project-form";
import type { ProjectDetail } from "@/lib/types";

const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

type AudioStagePanelProps = {
  project: ProjectDetail;
  onUpdated: (project: ProjectDetail) => void;
};

export function AudioStagePanel({ project, onUpdated }: AudioStagePanelProps) {
  const mode = audioGenerationModeOf(project.automation_config);
  if (mode === "user_upload") {
    return <UploadAudioPanel project={project} onUpdated={onUpdated} />;
  }
  return <ElevenLabsPanel project={project} onUpdated={onUpdated} />;
}

function ElevenLabsPanel({ project, onUpdated }: AudioStagePanelProps) {
  const [voices, setVoices] = useState<{ id: string; name: string }[]>([]);
  const [voiceId, setVoiceId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void listAudioVoices(project.id)
      .then((rows) => {
        if (cancelled) return;
        setVoices(rows);
        setVoiceId((current) => current || rows[0]?.id || "");
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Não foi possível carregar as vozes");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  async function onGenerate() {
    if (!voiceId) return;
    setBusy(true);
    setError(null);
    try {
      onUpdated(await generateProjectAudio(project.id, voiceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível gerar o áudio");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-white/45">
        Escolha a voz da ElevenLabs. Depois da geração, o áudio é re-transcrito para alinhar os
        tempos das cenas.
      </p>
      <label className="label-tech block">
        Voz
        <select
          value={voiceId}
          onChange={(event) => setVoiceId(event.target.value)}
          disabled={loading || voices.length === 0}
          className={`${FIELD} disabled:cursor-not-allowed disabled:opacity-50`}
        >
          {voices.map((voice) => (
            <option key={voice.id} value={voice.id}>
              {voice.name}
            </option>
          ))}
        </select>
      </label>
      {error ? <p className="font-mono text-xs text-red-300">{error}</p> : null}
      <button
        type="button"
        disabled={busy || loading || !voiceId}
        onClick={() => void onGenerate()}
        className="w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50 sm:w-auto"
      >
        {busy ? "Gerando…" : "Gerar áudio"}
      </button>
    </div>
  );
}

function UploadAudioPanel({ project, onUpdated }: AudioStagePanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onConfirm() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onUpdated(await uploadProjectAudio(project.id, file));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível enviar o áudio");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-white/45">
        Envie o áudio final. Ele será re-transcrito (Whisper) para alinhar os timestamps das cenas
        antes do render.
      </p>
      <label className="label-tech block">
        Arquivo de áudio
        <input
          type="file"
          accept="audio/*"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className={`${FIELD} file:mr-3 file:rounded file:border-0 file:bg-brass-500 file:px-2 file:py-1 file:font-mono file:text-[10px] file:tracking-wide file:text-ink-950`}
        />
      </label>
      {error ? <p className="font-mono text-xs text-red-300">{error}</p> : null}
      <button
        type="button"
        disabled={busy || !file}
        onClick={() => void onConfirm()}
        className="w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50 sm:w-auto"
      >
        {busy ? "Enviando…" : "Confirmar áudio"}
      </button>
    </div>
  );
}
