FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
# YouTube muda o nsig com frequência. Bump YTDLP_VERSION para invalidar o cache desta camada.
ARG YTDLP_VERSION=2026.8.19
RUN poetry install --no-ansi --no-root --only main \
    && pip install --no-cache-dir --force-reinstall "yt-dlp[default,deno]==${YTDLP_VERSION}"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
