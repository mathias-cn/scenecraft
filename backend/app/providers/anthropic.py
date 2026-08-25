from app.core.config import settings

STUB_PREFIX = "[stub]"


def generate_script(*, title: str, prompt: str) -> str:
    """Gera o roteiro do vídeo via Anthropic. Sem chave, devolve um stub."""
    if not settings.anthropic_api_key or settings.anthropic_api_key.startswith("your_"):
        return (
            f"{STUB_PREFIX} Roteiro para «{title}».\n\n"
            f"Abertura: {prompt}\n\n"
            "Desenvolvimento: explique a ideia em 3 blocos curtos.\n"
            "Fechamento: convite para se inscrever no canal.\n"
        )

    import anthropic as anthropic_sdk

    client = anthropic_sdk.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1200,
        messages=[
            {
                "role": "user",
                "content": (
                    "Escreva um roteiro falado (narração) para um vídeo curto de YouTube. "
                    f"Título: {title}\n\nIdeia: {prompt}\n\n"
                    "Responda só com o texto da narração, em português."
                ),
            }
        ],
    )
    return "".join(block.text for block in message.content if getattr(block, "text", None))
