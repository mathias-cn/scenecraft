# SceneCraft

Sistema pessoal de geração automatizada de vídeos para YouTube.

O pipeline pega uma ideia, escreve o roteiro (LLM), gera a narração (ElevenLabs), produz o vídeo (Higgsfield) e armazena o media (S3 / Cloudflare R2). O pacote final (MP4, título, descrição e tags) fica pronto para colar no YouTube Studio.

```
frontend (Next.js)  →  api (FastAPI)
                           ↓
                      redis + workers Celery (filas por tipo de job)
                           ↓
                      Supabase Postgres (gerenciado, não self-hosted)
                           ↓
              OpenAI · ElevenLabs · Higgsfield · S3/R2
```

## Layout do backend

| Pasta | Papel |
| --- | --- |
| `app/api` | Routers FastAPI (`/health`, `/api/projects`, `/api/jobs`) |
| `app/tasks` | Tasks Celery (uma por fila) |
| `app/models` | SQLAlchemy + enums Postgres |
| `app/core` | Config, filas, máquina de estados, rate limiter Redis |
| `app/celery_app.py` | Broker/result Redis e `task_queues` / `task_routes` |
| `app/worker.py` | Sobe um worker por fila com concorrência independente |

## Stack

| Parte | Tecnologia |
| --- | --- |
| `/backend` | Python 3.11, FastAPI, Celery, SQLAlchemy, Alembic, Poetry |
| `/frontend` | Next.js 14, TypeScript, App Router |
| Banco | **Supabase Postgres** (gerenciado, não self-hosted — em dev e em produção) |
| Infra local | Redis 7, Docker Compose (sem Postgres) |

## Requisitos

Antes de subir a API, o worker ou o Compose, você precisa de:

1. Um **projeto Supabase** com Postgres (o SceneCraft **não** sobe Postgres local).
2. Docker Desktop (ou Docker Engine + Compose v2), se for usar o `docker compose`.
3. Um `.env` na raiz com `DATABASE_URL` e `DATABASE_URL_MIGRATIONS` apontando para esse projeto.
4. Credenciais OAuth do Google e `OWNER_EMAIL` (veja [Autenticação](#autenticação)).

## Autenticação

O SceneCraft é um sistema pessoal: o login com Google (Better Auth) **só aceita um email**, o do dono, definido em `OWNER_EMAIL`. Qualquer outra conta Google é recusada no frontend e na API. Use o mesmo valor no frontend e no backend.

No [Google Cloud Console](https://console.cloud.google.com/) (APIs e serviços → Credenciais → cliente OAuth 2.0), autorize a redirect URI:

```
https://scenecraft.mazting.studio/api/auth/callback/google
```

Em desenvolvimento local, autorize também `http://localhost:3000/api/auth/callback/google`.

Variáveis no `.env` da raiz (veja `.env.example`): `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OWNER_EMAIL`. Gere o secret com `openssl rand -base64 32`. Em produção, `BETTER_AUTH_URL` deve ser `https://scenecraft.mazting.studio`.

## Banco de dados (Supabase)

O Postgres é **sempre** o do Supabase. Não existe serviço `postgres` no `docker-compose.yml`. A API e os workers conectam só via `DATABASE_URL` / `DATABASE_URL_MIGRATIONS`.

1. Crie um projeto em [supabase.com/dashboard](https://supabase.com/dashboard).
2. Em **Project Settings → Data API** (ou API), **desabilite**:
   - **Enable Data API**
   - **Automatically expose new tables** (e equivalentes de exposição automática do schema)

   O backend acessa o banco só pela connection string (SQLAlchemy / Alembic). PostgREST e a Data API não são usados.
3. Em **Project Settings → Database**, copie as duas URIs:
   - **Direct connection** — porta **5432** → `DATABASE_URL_MIGRATIONS` (Alembic). DDL, `pg_advisory_lock` e migrations precisam de sessão direta, não do pooler em modo transaction.
   - **Connection pooling** (Supavisor) — porta **6543** → `DATABASE_URL` (FastAPI e workers Celery).
4. Cole no `.env` e mantenha `sslmode=require` (obrigatório no Supabase). Se a senha tiver caracteres especiais, use URL-encoding.

```bash
cp .env.example .env
```

No PowerShell:

```powershell
Copy-Item .env.example .env
```

Exemplo (troque `PROJECT_REF`, `REGION` e a senha):

```
DATABASE_URL=postgresql://postgres.PROJECT_REF:YOUR_PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require
DATABASE_URL_MIGRATIONS=postgresql://postgres:YOUR_PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres?sslmode=require
```

A API aplica as migrations na subida (`alembic upgrade head`) usando `DATABASE_URL_MIGRATIONS`. A aplicação usa `DATABASE_URL` com `pool_pre_ping` e pool pequeno (`pool_size=5`, `max_overflow=10`), porque o pooler do Supabase também limita conexões.

## Subir tudo com Docker Compose

Com o `.env` já preenchido com as URIs do Supabase:

```bash
docker compose up --build
```

Na primeira execução o Compose constrói as imagens, sobe o Redis, aplica as migrations **no Supabase** e inicia o pipeline.

Abra:

| Serviço | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| Docs (Swagger) | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
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

## Serviços no `docker-compose.yml`

- **api** — FastAPI (`uvicorn`), porta `8000` (roda Alembic no Supabase antes de subir)
- **worker** — um processo Celery por fila (`transcribe`, `scene_planning`, `media_gen`, `audio_gen`, `render`, `thumbnail`, `description`), cada um com concorrência via env
- **redis** — broker e backend de resultados do Celery
- **frontend** — Next.js 14, porta `3000`

Não há Postgres neste arquivo: o banco é o projeto Supabase configurado no `.env`.

O ingest de YouTube usa **yt-dlp**. O YouTube muda o algoritmo de assinatura (`nsig`) com frequência e quebra extratores antigos — isso não é um bug pontual, é manutenção recorrente. Atualize `yt-dlp` no `backend/pyproject.toml` / `backend/poetry.lock` **pelo menos uma vez por mês** (`cd backend && poetry update yt-dlp`) e reconstrua `api`/`worker` **sem cache** dessa camada:

```bash
docker compose build --no-cache api worker
```

Em produção, o mesmo vale com `docker compose -f docker-compose.prod.yml build --no-cache api worker`. A partir de 2025/2026 o nsig também exige o extra `yt-dlp-ejs` e um runtime JS (incluídos via `yt-dlp[default,deno]`). Se o log mostrar `nsig extraction failed` / `Requested format is not available` / `Only images are available`, a versão do yt-dlp (ou o runtime JS) está desatualizada.

## Variáveis de ambiente

Veja `.env.example`. As principais:

| Variável | Uso |
| --- | --- |
| `DATABASE_URL` | Pooler Supabase (`6543`) — FastAPI e Celery |
| `DATABASE_URL_MIGRATIONS` | Conexão direta Supabase (`5432`) — Alembic |
| `REDIS_URL` | Broker e result backend do Celery |
| `CELERY_CONCURRENCY_*` | Concorrência por fila (ex. `CELERY_CONCURRENCY_MEDIA_GEN=1`) |
| `CELERY_TASK_MAX_RETRIES` | Retries Celery após a 1ª execução (padrão `2` = 3 tentativas) |
| `PROVIDER_CONCURRENCY_*` | Semáforo Redis por provider (`higgsfield`, `elevenlabs`, `openai`, `r2`) |
| `RATE_LIMIT_*` | Teto de jobs por janela Redis (`RATE_LIMIT_WINDOW_SECONDS`) |
| `HIGGSFIELD_API_KEY` | Geração de vídeo |
| `ELEVENLABS_API_KEY` | TTS / narração |
| `OPENAI_API_KEY` | Whisper, LLM e imagens |
| `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL` | S3 ou R2 |
| `R2_ACCOUNT_ID` | Conta Cloudflare R2 |
| `BETTER_AUTH_SECRET` | Secret do Better Auth (`openssl rand -base64 32`) |
| `BETTER_AUTH_URL` | URL pública do frontend (prod: `https://scenecraft.mazting.studio`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Cliente OAuth 2.0 no Google Cloud Console |
| `OWNER_EMAIL` | Único email autorizado a entrar |

Se `S3_ENDPOINT_URL` estiver vazio, o storage usa AWS S3. Para R2, use `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`.

O teto diário de custo estimado fica na tabela `app_settings` (não em variável de ambiente) e pode ser editado em **Configurações**, sem redeploy.

## Desenvolvimento local (sem Docker para o app)

Redis ainda pode vir do Compose:

```bash
docker compose up redis -d
```

**Backend** (Poetry):

```bash
cd backend
poetry install
# DATABASE_URL e DATABASE_URL_MIGRATIONS vêm do .env na raiz (Supabase)
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --port 8000
poetry run python -m app.worker
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

O dashboard espera a API em `NEXT_PUBLIC_API_URL` (padrão `http://localhost:8000`).

## Deploy em VPS (Ubuntu)

Produção usa `docker-compose.prod.yml` (sem Postgres local, Redis só na rede interna, frontend com `next start`). Guia, firewall ufw e script: [`deploy/README.md`](deploy/README.md).
