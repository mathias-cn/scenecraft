"use client";

import { useEffect, useState } from "react";

import { listImageModels } from "@/lib/api";
import {
  IMAGE_QUALITIES,
  OPENAI_IMAGE_MODELS,
  type ImageProviderName,
  type ImageQuality,
} from "@/lib/project-form";
import type { ImageModelOption } from "@/lib/types";

const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

type ImageModelPickerProps = {
  provider: ImageProviderName;
  model: string;
  quality: ImageQuality;
  onModelChange: (model: string) => void;
  onQualityChange: (quality: ImageQuality) => void;
};

export function ImageModelPicker({
  provider,
  model,
  quality,
  onModelChange,
  onQualityChange,
}: ImageModelPickerProps) {
  const [models, setModels] = useState<ImageModelOption[]>(
    provider === "openai" ? [...OPENAI_IMAGE_MODELS] : [],
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(provider === "higgsfield");

  useEffect(() => {
    if (provider !== "higgsfield") {
      setModels([...OPENAI_IMAGE_MODELS]);
      setLoading(false);
      setError(null);
      if (!OPENAI_IMAGE_MODELS.some((item) => item.id === model)) {
        onModelChange(OPENAI_IMAGE_MODELS[0].id);
      }
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void listImageModels("higgsfield")
      .then((next) => {
        if (cancelled) return;
        setModels(next);
        if (next.length && !next.some((item) => item.id === model)) {
          onModelChange(next[0].id);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Não foi possível listar os modelos Higgsfield");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Catálogo só recarrega quando o provider muda.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  return (
    <div className="mt-4">
      <label className="label-tech block">
        Modelo
        <select
          value={model}
          onChange={(event) => onModelChange(event.target.value)}
          disabled={loading || models.length === 0}
          className={FIELD}
        >
          {models.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {provider === "openai" ? (
        <label className="label-tech mt-4 block">
          Quality
          <select
            value={quality}
            onChange={(event) => onQualityChange(event.target.value as ImageQuality)}
            className={FIELD}
          >
            {IMAGE_QUALITIES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {loading ? <p className="mt-2 font-mono text-[10px] text-white/35">Carregando modelos…</p> : null}
      {error ? <p className="mt-2 font-mono text-xs text-red-300">{error}</p> : null}
    </div>
  );
}
