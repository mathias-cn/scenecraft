"""Estimativas de custo (USD) para Higgsfield, ElevenLabs e LLM.

Valores são tabelas públicas de pricing, não a fatura real do provider.
`Numeric(12, 6)` no banco guarda até micros de dólar.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

USD_QUANT = Decimal("0.000001")

# OpenAI Chat Completions: (input, output) USD / 1M tokens.
LLM_USD_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-5-nano": (Decimal("0.05"), Decimal("0.40")),
    "gpt-5-mini": (Decimal("0.25"), Decimal("2.00")),
    "gpt-5": (Decimal("1.25"), Decimal("10.00")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
}
_DEFAULT_LLM_RATE = LLM_USD_PER_MILLION["gpt-4o-mini"]

# ElevenLabs eleven_multilingual_v2 (plano Creator): US$ 0.30 / 1k caracteres.
ELEVENLABS_USD_PER_1K_CHARS = Decimal("0.30")

# Fallback quando a Higgsfield não devolve cost no payload.
HIGGSFIELD_IMAGE_USD = Decimal("0.03")

# OpenAI Whisper whisper-1: US$ 0.006 / minuto de áudio.
WHISPER_USD_PER_MINUTE = Decimal("0.006")

_CHARS_PER_TOKEN = 4


def as_usd(value: Any) -> Decimal:
    """Normaliza um número para Numeric(12, 6). None vira 0."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value))
        except Exception:
            return Decimal("0")
    return amount.quantize(USD_QUANT, rounding=ROUND_HALF_UP)


def add_usd(*values: Any) -> Decimal:
    total = Decimal("0")
    for value in values:
        total += as_usd(value)
    return as_usd(total)


def add_project_llm_cost(project: Any, amount: Any) -> Decimal:
    """Acumula custo de LLM sem entidade própria (tradução, scene planning)."""
    total = add_usd(getattr(project, "llm_cost_usd", None), amount)
    project.llm_cost_usd = total
    return total


def estimate_tokens(text: str | None) -> int:
    raw = text or ""
    if not raw:
        return 0
    return max(1, (len(raw) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def _llm_rate(model: str | None) -> tuple[Decimal, Decimal]:
    key = (model or "").strip().lower()
    if key in LLM_USD_PER_MILLION:
        return LLM_USD_PER_MILLION[key]
    for name, rate in LLM_USD_PER_MILLION.items():
        if key.startswith(name):
            return rate
    return _DEFAULT_LLM_RATE


def estimate_llm_cost_usd(
    model: str | None,
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> Decimal:
    input_rate, output_rate = _llm_rate(model)
    million = Decimal("1000000")
    prompt = Decimal(max(0, int(prompt_tokens)))
    completion = Decimal(max(0, int(completion_tokens)))
    return as_usd((prompt * input_rate + completion * output_rate) / million)


def estimate_llm_cost_from_text(
    model: str | None,
    system_prompt: str,
    user_content: str,
    completion: str | Mapping[str, Any] | None,
) -> Decimal:
    if isinstance(completion, Mapping):
        import json

        output = json.dumps(completion, ensure_ascii=False)
    else:
        output = str(completion or "")
    return estimate_llm_cost_usd(
        model,
        prompt_tokens=estimate_tokens(system_prompt) + estimate_tokens(user_content),
        completion_tokens=estimate_tokens(output),
    )


def usage_tokens(usage: Any) -> tuple[int, int]:
    """Lê prompt/completion tokens do objeto `usage` da OpenAI (v1 ou nomes novos)."""
    if usage is None:
        return 0, 0
    if isinstance(usage, Mapping):
        prompt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        return int(prompt or 0), int(completion or 0)
    prompt = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None) or 0
    completion = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None) or 0
    return int(prompt or 0), int(completion or 0)


def estimate_whisper_cost_usd(*, duration_ms: int = 0) -> Decimal:
    """Custo Whisper-1 pelo minuto (e fração) de áudio processado."""
    minutes = Decimal(max(0, int(duration_ms))) / Decimal("60000")
    return as_usd(minutes * WHISPER_USD_PER_MINUTE)


def add_cost(obj: Any, amount: Any, field: str = "cost_usd") -> Decimal:
    total = add_usd(getattr(obj, field, None), amount)
    setattr(obj, field, total)
    return total


def estimate_elevenlabs_cost_usd(text: str | None) -> Decimal:
    chars = Decimal(len(text or ""))
    return as_usd(chars * ELEVENLABS_USD_PER_1K_CHARS / Decimal("1000"))


def estimate_higgsfield_cost_usd(payload: Mapping[str, Any] | None, model: str | None = None) -> Decimal:
    data = payload or {}
    for key in ("cost_usd", "cost", "price_usd"):
        value = data.get(key)
        if value is None:
            continue
        try:
            return as_usd(value)
        except Exception:
            continue
    _ = model
    return as_usd(HIGGSFIELD_IMAGE_USD)


class PricedText:
    """Texto gerado por LLM com custo estimado da completion."""

    def __init__(self, text: str, cost_usd: Any = 0) -> None:
        self.text = text
        self.cost_usd = as_usd(cost_usd)

    def __str__(self) -> str:
        return self.text


def unpack_priced_text(raw: Any) -> tuple[str, Decimal]:
    """Aceita PricedText, str (mocks) ou dict `{text, cost_usd}`."""
    if raw is None:
        return "", Decimal("0")
    if isinstance(raw, PricedText):
        return raw.text, raw.cost_usd
    if isinstance(raw, Mapping) and "text" in raw:
        return str(raw.get("text") or ""), as_usd(raw.get("cost_usd"))
    return str(raw), Decimal("0")


class PricedSequence(list):
    """Lista com `.cost_usd` da(s) completion(s) que a geraram."""

    def __init__(self, items: list[Any], cost_usd: Any = 0) -> None:
        super().__init__(items)
        self.cost_usd = as_usd(cost_usd)
