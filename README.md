# SceneCraft

Sistema pessoal de geração automatizada de vídeos para YouTube.

O pipeline pega uma ideia, escreve o roteiro (Anthropic), gera a narração (ElevenLabs), produz o vídeo (Higgsfield), armazena o media (S3 / Cloudflare R2) e publica no YouTube.

```
frontend (Next.js)  →  api (FastAPI)  →  Supabase Postgres
                           ↓
                      redis + worker (Celery)
                           ↓
              Anthropic · ElevenLabs · Higgsfield · YouTube · S3/R2
```

## Stack

| Parte | Tecnologia |
| --- | --- |
| `/backend` | Python 3.11, FastAPI, Celery, SQLAlchemy, Alembic, Poetry |
| `/frontend` | Next.js 14, TypeScript, App Router |
| Banco | Supabase Postgres (conexão direta + pooler) |
| Infra local | Redis 7, Docker Compose |

## Banco de dados (Supabase)

O Postgres **não** sobe no Docker Compose. Crie um projeto no [Supabase](https://supabase.com) e use as connection strings do painel.

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

**Requisitos:** Docker Desktop (ou Docker Engine + Compose v2) e o `.env` preenchido com as URIs do Supabase.

```bash
docker compose up --build
```

Na primeira execução o Compose constrói as imagens, sobe o Redis, aplica as migrations no Supabase e inicia o pipeline.

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

- **api** — FastAPI (`uvicorn`), porta `8000` (roda Alembic antes de subir)
- **worker** — Celery worker (fila de geração de vídeos)
- **redis** — broker e backend de resultados do Celery
- **frontend** — Next.js 14, porta `3000`

Há um bloco **comentado** de Postgres local no compose, só para desenvolvimento sem internet. Nesse caso use `sslmode=disable` nas duas URLs.

## Variáveis de ambiente

Veja `.env.example`. As principais:

| Variável | Uso |
| --- | --- |
| `DATABASE_URL` | Pooler Supabase (`6543`) — FastAPI e Celery |
| `DATABASE_URL_MIGRATIONS` | Conexão direta Supabase (`5432`) — Alembic |
| `REDIS_URL` | Celery broker / resultados |
| `HIGGSFIELD_API_KEY` | Geração de vídeo |
| `ELEVENLABS_API_KEY` | TTS / narração |
| `ANTHROPIC_API_KEY` | Roteiro |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` | Upload OAuth |
| `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL` | S3 ou R2 |
| `R2_ACCOUNT_ID` | Conta Cloudflare R2 |

Se `S3_ENDPOINT_URL` estiver vazio, o storage usa AWS S3. Para R2, use `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`.

## Desenvolvimento local (sem Docker para o app)

Redis ainda pode vir do Compose:

```bash
docker compose up redis -d
```

**Backend** (Poetry):

```bash
cd backend
poetry install
# DATABASE_URL e DATABASE_URL_MIGRATIONS vêm do .env na raiz
poetry run alembic upgrade head
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
