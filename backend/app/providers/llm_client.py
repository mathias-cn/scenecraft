"""Completions estruturadas via OpenAI Chat Completions (JSON nativo).

`structured_completion` é o método único reutilizado para:
- agrupar transcript em scenes (só source_segment_ids + visual_prompt)
- traduzir cada segmento (preservando start_ms/end_ms)
- gerar a descrição do vídeo e as tags SEO a partir do transcript completo
- resumir o vídeo e montar o prompt da thumbnail
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Mapping, Sequence

from app.providers.openai_auth import OpenAIKeyError, openai_client

CHAT_MODEL = "gpt-4o-mini"
TRANSLATE_BATCH_SIZE = 20

PLAN_SCENES_SYSTEM = """Você agrupa segmentos de transcript em cenas visuais para um vídeo.
Responda só com um objeto JSON na forma:
{"scenes":[{"source_segment_ids":[0,1],"visual_prompt":"..."}]}
Regras:
- Decida APENAS o agrupamento: quais índices de segmento (marcados como [n] no transcript) formam cada cena.
- NUNCA gere start_ms, end_ms nem qualquer timestamp. O código calcula os tempos depois.
- source_segment_ids usa os índices cobertos, em ordem crescente, contíguos, sem repetir e sem pular.
- Cada segmento do transcript entra em exatamente uma cena; não deixe sobra nem duplicata.
- Corte em pontos naturais de fim de frase ou ideia, não no meio de uma sentença.
- Respeite min_duration_ms e max_duration_ms do JSON de entrada: a duração de cada cena é a soma das durações reais (ms) dos segmentos incluídos.
- visual_prompt em inglês, concreto, para gerar imagem ou vídeo (sujeito, ambiente, câmera, iluminação)."""

TRANSLATE_SYSTEM = """Você traduz cada segmento de transcript para o idioma pedido.
Responda só com um objeto JSON na forma:
{"segments":[{"index":0,"start_ms":0,"end_ms":0,"text_translated":"..."}]}
Regras:
- Um item de saída por segmento de entrada, mesmo index.
- Copie start_ms e end_ms exatamente como no input; não altere timestamps.
- text_translated é só a tradução do texto; não junte nem divida segmentos."""

DESCRIPTION_SYSTEM = """Você escreve a descrição e as tags de um vídeo para o YouTube a partir do transcript.
Responda só com um objeto JSON na forma:
{"text":"...","tags":["..."]}
Regras:
- text é UM parágrafo otimizado para YouTube: resumo do conteúdo e, se fizer sentido, um call-to-action (inscrever, comentar, assistir outro vídeo). Sem timestamps e sem hashtags no texto.
- tags: 10 a 15 palavras-chave no formato do campo de tags do YouTube (sem #, sem vírgula dentro da tag; espaços entre palavras são permitidos).
- Idioma da descrição e das tags = idioma pedido no JSON de entrada."""

TITLE_SYSTEM = """Você sugere títulos de YouTube a partir de um rascunho.
Responda só com um objeto JSON na forma:
{"titles":["...","...","..."]}
Regras:
- Exatamente 3 títulos, distintos entre si.
- Mesmo idioma do rascunho.
- Tema e tom similares ao rascunho; não fuja do assunto.
- Curtos, específicos, sem aspas, sem numeração, sem hashtag.
- Cada título cabe em uma linha (no máximo ~70 caracteres)."""

SUMMARY_SYSTEM = """Você resume o conteúdo de um vídeo a partir do transcript.
Responda só com um objeto JSON na forma:
{"summary":"..."}
Regras:
- summary em 2–4 frases, no idioma pedido.
- Foque no tema, no gancho e na conclusão; sem timestamps nem lista de cenas."""

THUMBNAIL_PROMPT_SYSTEM = """Você cria um prompt de imagem para thumbnail de YouTube.
Responda só com um objeto JSON na forma:
{"prompt":"..."}
Regras:
- prompt em inglês, cinematográfico, alto contraste, composição 16:9 (1280x720).
- Sem texto na imagem (no titles, captions, letters or watermarks).
- Sujeito nítido, expressão chamativa, fundo simples e legível em miniatura.
- Se o JSON trouxer personagem ou estilo, inclua-os no prompt."""

DEFAULT_TITLE_MODEL = "gpt-5-nano"


class LLMError(ValueError):
    """Falha no cliente LLM."""


class LLMJSONError(LLMError):
    """A OpenAI não devolveu um objeto JSON válido."""


class LLMProvider(ABC):
    """Interface de completion JSON. Trocar de provider não muda quem chama as helpers."""

    @abstractmethod
    def structured_completion(
        self,
        system_prompt: str,
        user_content: str,
        *,
        model: str | None = None,
    ) -> dict:
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

    def structured_completion(
        self,
        system_prompt: str,
        user_content: str,
        *,
        model: str | None = None,
    ) -> dict:
        response = self._client_or_default().chat.completions.create(
            model=(model or CHAT_MODEL).strip() or CHAT_MODEL,
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


def structured_completion(
    system_prompt: str,
    user_content: str,
    *,
    model: str | None = None,
) -> dict:
    """Chat Completions com `response_format={"type": "json_object"}`."""
    return get_llm_provider().structured_completion(system_prompt, user_content, model=model)


def _segment_payload(segment: Mapping[str, Any], index: int) -> dict[str, Any]:
    text = segment.get("text") or segment.get("text_original") or ""
    return {
        "index": int(segment["index"]) if "index" in segment else index,
        "start_ms": int(segment["start_ms"]),
        "end_ms": int(segment["end_ms"]),
        "text": str(text),
    }


def _format_timestamp_ms(ms: int) -> str:
    total = max(0, int(ms))
    millis = total % 1000
    minutes, seconds = divmod(total // 1000, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def transcript_timeline(segments: Sequence[Mapping[str, Any]]) -> str:
    """Transcript completo com índice e timestamps, para o LLM agrupar sem inventar tempos."""
    lines: list[str] = []
    for index, segment in enumerate(segments):
        idx = int(segment["index"]) if "index" in segment else index
        start = int(segment["start_ms"])
        end = int(segment["end_ms"])
        text = str(segment.get("text") or segment.get("text_original") or "")
        duration = max(0, end - start)
        lines.append(
            f"[{idx}] {_format_timestamp_ms(start)}–{_format_timestamp_ms(end)} ({duration}ms) {text}"
        )
    return "\n".join(lines)


def plan_scenes(
    segments: Sequence[Mapping[str, Any]],
    *,
    language: str = "pt-BR",
    character_description: str | None = None,
    style_name: str | None = None,
    scene_pacing: str = "medium",
    min_duration_ms: int = 15_000,
    max_duration_ms: int = 25_000,
) -> list[dict[str, Any]]:
    """Pede ao LLM só o agrupamento (source_segment_ids + visual_prompt). Sem timestamps."""
    payload: dict[str, Any] = {
        "language": language,
        "scene_pacing": scene_pacing,
        "min_duration_ms": int(min_duration_ms),
        "max_duration_ms": int(max_duration_ms),
        "instruction": (
            "Group contiguous segment indexes into scenes. "
            "Return only source_segment_ids and visual_prompt. "
            "Never return start_ms or end_ms."
        ),
        "transcript": transcript_timeline(segments),
    }
    if character_description:
        payload["character"] = {
            "description": character_description,
            "instruction": "Every visual_prompt must feature this same recurring character as the subject.",
        }
    if style_name:
        payload["visual_style"] = style_name
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
        if character_description and character_description.lower() not in prompt.lower():
            prompt = f"{prompt.rstrip('.')}. Recurring character: {character_description.strip()}"
        if style_name and style_name.lower() not in prompt.lower():
            prompt = f"{prompt.rstrip('.')}. Visual style: {style_name.strip()}"
        ids = raw.get("source_segment_ids") or []
        if not isinstance(ids, list) or not ids:
            raise LLMJSONError(f"cena {index} sem source_segment_ids")
        normalized.append(
            {
                "source_segment_ids": [int(item) for item in ids],
                "visual_prompt": prompt,
            }
        )
    return normalized


def translate_segments(
    segments: Sequence[Mapping[str, Any]],
    *,
    target_language: str,
    batch_size: int = TRANSLATE_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """Traduz cada segmento e preserva start_ms/end_ms do original.

    Lotes de `batch_size` (padrão 20) evitam estourar o contexto em transcripts longos.
    """
    originals = [_segment_payload(segment, index) for index, segment in enumerate(segments)]
    if not originals:
        return []
    size = max(1, int(batch_size))
    translated: list[dict[str, Any]] = []
    for start in range(0, len(originals), size):
        translated.extend(
            _translate_batch(originals[start : start + size], target_language=target_language)
        )
    return translated


def _translate_batch(
    originals: list[dict[str, Any]],
    *,
    target_language: str,
) -> list[dict[str, Any]]:
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
) -> dict[str, Any]:
    """Gera descrição YouTube + tags SEO a partir do transcript (um único JSON)."""
    text = (transcript or "").strip()
    if not text:
        raise LLMError("transcript vazio para gerar descrição")
    payload = {"title": title, "language": language, "transcript": text}
    result = structured_completion(DESCRIPTION_SYSTEM, json.dumps(payload, ensure_ascii=False))
    body = str(result.get("text") or result.get("description") or "").strip()
    if not body:
        raise LLMJSONError("JSON de descrição deve conter 'text'")
    return {
        "text": body,
        "tags": normalize_youtube_tags(result.get("tags")),
        "title": str(result.get("title") or title).strip() or title,
    }


MIN_YOUTUBE_TAGS = 10
MAX_YOUTUBE_TAGS = 15


def normalize_youtube_tags(raw: Any) -> list[str]:
    """Limpa tags no formato do campo YouTube: sem #, sem duplicata, 10–15 itens."""
    if not isinstance(raw, list):
        raise LLMJSONError("JSON de descrição deve conter a lista 'tags'")
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = " ".join(str(item or "").replace(",", " ").split())
        if text.startswith("#"):
            text = text.lstrip("#").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(text)
        if len(tags) == MAX_YOUTUBE_TAGS:
            break
    if len(tags) < MIN_YOUTUBE_TAGS:
        raise LLMJSONError("JSON de descrição deve conter 10 a 15 tags")
    return tags


def summarize_video(
    *,
    title: str,
    transcript: str,
    language: str = "pt-BR",
) -> str:
    """Resume o vídeo a partir do transcript completo."""
    text = (transcript or "").strip()
    if not text:
        raise LLMError("transcript vazio para resumir")
    payload = {"title": title, "language": language, "transcript": text}
    result = structured_completion(SUMMARY_SYSTEM, json.dumps(payload, ensure_ascii=False))
    summary = str(result.get("summary") or result.get("text") or "").strip()
    if not summary:
        raise LLMJSONError("JSON de resumo deve conter 'summary'")
    return summary


def thumbnail_prompt(
    *,
    summary: str,
    title: str,
    character_description: str | None = None,
    style_name: str | None = None,
) -> str:
    """Monta um prompt de thumbnail chamativa a partir do resumo do vídeo."""
    text = (summary or "").strip()
    if not text:
        raise LLMError("resumo vazio para thumbnail")
    payload: dict[str, Any] = {
        "title": title,
        "summary": text,
        "instruction": "YouTube thumbnail, 16:9, no text in the image.",
    }
    if character_description:
        payload["character"] = character_description
    if style_name:
        payload["visual_style"] = style_name
    result = structured_completion(THUMBNAIL_PROMPT_SYSTEM, json.dumps(payload, ensure_ascii=False))
    prompt = str(result.get("prompt") or result.get("visual_prompt") or "").strip()
    if not prompt:
        raise LLMJSONError("JSON de thumbnail deve conter 'prompt'")
    return prompt


def title_model() -> str:
    from app.core.config import settings

    raw = str(getattr(settings, "openai_title_model", "") or "").strip()
    return raw or DEFAULT_TITLE_MODEL


def generate_titles(draft_title: str) -> list[str]:
    """Devolve 3 sugestões de título no mesmo tema/tom do rascunho."""
    draft = (draft_title or "").strip()
    if not draft:
        raise LLMError("draft_title vazio")
    payload = {"draft_title": draft, "count": 3}
    result = structured_completion(
        TITLE_SYSTEM,
        json.dumps(payload, ensure_ascii=False),
        model=title_model(),
    )
    raw = result.get("titles")
    if not isinstance(raw, list):
        raise LLMJSONError("JSON de títulos deve conter a lista 'titles'")
    titles: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip().strip('"').strip("'")
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        titles.append(text)
        if len(titles) == 3:
            break
    if len(titles) < 3:
        raise LLMJSONError("JSON de títulos deve conter 3 títulos")
    return titles
