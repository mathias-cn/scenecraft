"""Completions estruturadas via OpenAI Chat Completions (JSON nativo)."""

from __future__ import annotations

import json

from app.core.config import settings

CHAT_MODEL = "gpt-4o-mini"


class LLMJSONError(ValueError):
    """A OpenAI não devolveu um objeto JSON válido."""


def _api_key() -> str:
    key = (settings.openai_api_key or "").strip()
    if not key or key.startswith("your_"):
        raise LLMJSONError("OPENAI_API_KEY não configurada")
    return key


def _openai_client():
    key = _api_key()
    from openai import OpenAI

    return OpenAI(api_key=key)


def structured_completion(system_prompt: str, user_content: str) -> dict:
    """Chama o chat da OpenAI forçando `response_format=json_object` e devolve um dict.

    Usado pelos jobs de scene planning, tradução de transcript e geração de descrição.
    """
    response = _openai_client().chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
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
