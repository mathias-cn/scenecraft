"""Chave OpenAI compartilhada por transcrição (Whisper) e LLM (chat)."""

from __future__ import annotations

from app.core.config import settings


class OpenAIKeyError(RuntimeError):
    """OPENAI_API_KEY ausente ou placeholder."""


def openai_api_key() -> str:
    """Lê `OPENAI_API_KEY` via settings (`openai_api_key`)."""
    key = (settings.openai_api_key or "").strip()
    if not key or key.startswith("your_"):
        raise OpenAIKeyError("OPENAI_API_KEY não configurada")
    return key


def openai_client():
    from openai import OpenAI

    return OpenAI(api_key=openai_api_key())
