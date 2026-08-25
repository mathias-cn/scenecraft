# SceneCraft

Sistema pessoal de geração automatizada de vídeos para YouTube.

O pipeline pega uma ideia, escreve o roteiro (Anthropic), gera a narração (ElevenLabs), produz o vídeo (Higgsfield), armazena o media (S3 / Cloudflare R2) e publica no YouTube.

```
frontend (Next.js)  →  api (FastAPI)  →  postgres
                           ↓
                      redis + worker (Celery)
                           ↓
              Anthropic · ElevenLabs · Higgsfield · YouTube · S3/R2
```

## Stack

| Parte | Tecnologia |
| --- | --- |
| `/backend` | Python 3.11, FastAPI, Celery, SQLAlchemy, Poetry |
| `/frontend` | Next.js 14, TypeScript, App Router |
| Infra | Postgres 16, Redis 7, Docker Compose |

## Subir tudo com Docker Compose

**Requisitos:** Docker Desktop (ou Docker Engine + Compose v2).

1. Copie o arquivo de ambiente e preencha as chaves (pode deixar os placeholders se só quiser validar o stack — o worker usa stubs quando as APIs não estão configuradas):

```bash
cp .env.example .env
```

No PowerShell:

```powershell
Copy-Item .env.example .env
```

2. Suba os serviços:

```bash
docker compose up --build
```

Na primeira execução o Compose constrói as imagens da API, do worker e do frontend, sobe o Postgres e o Redis, e inicia o pipeline.

3. Abra:

| Serviço | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| Docs (Swagger) | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Postgres | `localhost:5432` |
| Redis | `localhost:6379` |

Para rodar em background:

```bash
docker compose up --build -d
```

Para ver logs:

```bash
docker compose logs -f api worker
```

Para parar:

```bash
docker compose down
```

Os dados do Postgres ficam no volume `postgres_data`. Para zerar o banco:

```bash
docker compose down -v
```

## Serviços no `docker-compose.yml`

- **api** — FastAPI (`uvicorn`), porta `8000`
- **worker** — Celery worker (fila de geração de vídeos)
- **postgres** — banco relacional
- **redis** — broker e backend de resultados do Celery
- **frontend** — Next.js 14, porta `3000`

## Variáveis de ambiente

Veja `.env.example`. As principais:

| Variável | Uso |
| --- | --- |
| `DATABASE_URL` | Postgres |
| `REDIS_URL` | Celery broker / resultados |
| `HIGGSFIELD_API_KEY` | Geração de vídeo |
| `ELEVENLABS_API_KEY` | TTS / narração |
| `ANTHROPIC_API_KEY` | Roteiro |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` | Upload OAuth |
| `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL` | S3 ou R2 |
| `R2_ACCOUNT_ID` | Conta Cloudflare R2 |

Se `S3_ENDPOINT_URL` estiver vazio, o storage usa AWS S3. Para R2, use `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`.

## Desenvolvimento local (sem Docker para o app)

Postgres e Redis ainda podem vir do Compose:

```bash
docker compose up postgres redis -d
```

**Backend** (Poetry):

```bash
cd backend
poetry install
# Ajuste DATABASE_URL / REDIS_URL para localhost no .env
poetry run uvicorn app.main:app --reload --port 8000
poetry run celery -A app.celery_app:celery_app worker --loglevel=info
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

O dashboard espera a API em `NEXT_PUBLIC_API_URL` (padrão `http://localhost:8000`).
