"""Completions estruturadas via OpenAI Chat Completions (JSON nativo).

`structured_completion` é o método único reutilizado para:
- agrupar transcript em scenes com visual_prompt
- traduzir cada segmento (preservando start_ms/end_ms)
- gerar a descrição do vídeo a partir do transcript completo
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Mapping, Sequence

from app.providers.openai_auth import OpenAIKeyError, openai_client

CHAT_MODEL = "gpt-4o-mini"

PLAN_SCENES_SYSTEM = """Você agrupa segmentos de transcript em cenas visuais para um vídeo.
Responda só com um objeto JSON na forma:
{"scenes":[{"index":0,"start_ms":0,"end_ms":0,"source_segment_ids":[0],"visual_prompt":"..."}]}
Regras:
- Cada cena cobre um ou mais segmentos contíguos.
- start_ms é o start_ms do primeiro segmento da cena; end_ms é o end_ms do último.
- source_segment_ids usa os index dos segmentos cobertos.
- visual_prompt em inglês, concreto, para gerar imagem ou vídeo (sujeito, ambiente, câmera, iluminação).
- index das cenas começa em 0 e é sequencial."""

TRANSLATE_SYSTEM = """Você traduz cada segmento de transcript para o idioma pedido.
Responda só com um objeto JSON na forma:
{"segments":[{"index":0,"start_ms":0,"end_ms":0,"text_translated":"..."}]}
Regras:
- Um item de saída por segmento de entrada, mesmo index.
- Copie start_ms e end_ms exatamente como no input; não altere timestamps.
- text_translated é só a tradução do texto; não junte nem divida segmentos."""

DESCRIPTION_SYSTEM = """Você escreve a descrição de um vídeo para o YouTube a partir do transcript.
Responda só com um objeto JSON na forma:
{"text":"...","title":"..."}
Regras:
- text é a descrição completa (parágrafos curtos, sem timestamps).
- title é um título opcional se o input não trouxer um bom título.
- Idioma da descrição = idioma pedido no JSON de entrada."""


class LLMError(ValueError):
    """Falha no cliente LLM."""


class LLMJSONError(LLMError):
    """A OpenAI não devolveu um objeto JSON válido."""


class LLMProvider(ABC):
    """Interface de completion JSON. Trocar de provider não muda quem chama as helpers."""

    @abstractmethod
    def structured_completion(self, system_prompt: str, user_content: str) -> dict:
        """Força JSON nativo da API e devolve um dict."""


def _parse_json_object(content: str | None) -> dict:
    if content is None or not str(content).strip():
        raise LLMJSONError("resposta da OpenAI veio vazia; esperado um objeto JSON")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMJSONError(
            f"resposta da OpenAI não é JSON válido: {exc.msg} (linha {exc.lineno}, coluna {exc.colno})"
        ) from exc
    if not isinstance(parsed, dict):
        raise LLMJSONError("resposta da OpenAI deve ser um objeto JSON, não uma lista ou escalar")
    return parsed


class OpenAILLMProvider(LLMProvider):
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _client_or_default(self):
        if self._client is not None:
            return self._client
        try:
            return openai_client()
        except OpenAIKeyError as exc:
            raise LLMError(str(exc)) from exc

    def structured_completion(self, system_prompt: str, user_content: str) -> dict:
        response = self._client_or_default().chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        return _parse_json_object(response.choices[0].message.content)


_provider: LLMProvider = OpenAILLMProvider()


def get_llm_provider() -> LLMProvider:
    return _provider


def set_llm_provider(provider: LLMProvider) -> None:
    if not isinstance(provider, LLMProvider):
        raise TypeError("provider must be a LLMProvider")
    global _provider
    _provider = provider


def structured_completion(system_prompt: str, user_content: str) -> dict:
    """Chat Completions com `response_format={"type": "json_object"}`."""
    return get_llm_provider().structured_completion(system_prompt, user_content)


def _segment_payload(segment: Mapping[str, Any], index: int) -> dict[str, Any]:
    text = segment.get("text") or segment.get("text_original") or ""
    return {
        "index": int(segment["index"]) if "index" in segment else index,
        "start_ms": int(segment["start_ms"]),
        "end_ms": int(segment["end_ms"]),
        "text": str(text),
    }


def plan_scenes(
    segments: Sequence[Mapping[str, Any]],
    *,
    language: str = "pt-BR",
) -> list[dict[str, Any]]:
    """Agrupa transcript_segments em cenas com visual_prompt."""
    payload = {
        "language": language,
        "segments": [_segment_payload(segment, index) for index, segment in enumerate(segments)],
    }
    result = structured_completion(PLAN_SCENES_SYSTEM, json.dumps(payload, ensure_ascii=False))
    scenes = result.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise LLMJSONError("JSON de scene planning deve conter a lista 'scenes'")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(scenes):
        if not isinstance(raw, dict):
            raise LLMJSONError("cada cena deve ser um objeto JSON")
        prompt = str(raw.get("visual_prompt") or "").strip()
        if not prompt:
            raise LLMJSONError(f"cena {index} sem visual_prompt")
        ids = raw.get("source_segment_ids") or []
        if not isinstance(ids, list):
            ids = []
        normalized.append(
            {
                "index": int(raw.get("index", index)),
                "start_ms": int(raw.get("start_ms", 0)),
                "end_ms": int(raw.get("end_ms", 0)),
                "source_segment_ids": [int(item) for item in ids],
                "visual_prompt": prompt,
            }
        )
    return normalized


def translate_segments(
    segments: Sequence[Mapping[str, Any]],
    *,
    target_language: str,
) -> list[dict[str, Any]]:
    """Traduz cada segmento e preserva start_ms/end_ms do original."""
    originals = [_segment_payload(segment, index) for index, segment in enumerate(segments)]
    payload = {"target_language": target_language, "segments": originals}
    result = structured_completion(TRANSLATE_SYSTEM, json.dumps(payload, ensure_ascii=False))
    rows = result.get("segments")
    if not isinstance(rows, list):
        raise LLMJSONError("JSON de tradução deve conter a lista 'segments'")
    by_index: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and "index" in row:
            by_index[int(row["index"])] = row
    translated: list[dict[str, Any]] = []
    for original in originals:
        row = by_index.get(original["index"], {})
        text = str(row.get("text_translated") or row.get("text") or "").strip()
        if not text:
            raise LLMJSONError(f"segmento {original['index']} sem text_translated")
        translated.append(
            {
                "index": original["index"],
                "start_ms": original["start_ms"],
                "end_ms": original["end_ms"],
                "text_original": original["text"],
                "text_translated": text,
            }
        )
    return translated


def generate_description(
    *,
    title: str,
    transcript: str,
    language: str = "pt-BR",
) -> dict[str, str]:
    """Gera a descrição do vídeo a partir do transcript completo."""
    payload = {"title": title, "language": language, "transcript": transcript}
    result = structured_completion(DESCRIPTION_SYSTEM, json.dumps(payload, ensure_ascii=False))
    text = str(result.get("text") or result.get("description") or "").strip()
    if not text:
        raise LLMJSONError("JSON de descrição deve conter 'text'")
    return {
        "text": text,
        "title": str(result.get("title") or title).strip() or title,
    }
