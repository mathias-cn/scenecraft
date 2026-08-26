# Deploy em VPS Ubuntu

Guia para subir o SceneCraft numa VPS Ubuntu 22.04 ou 24.04 com Docker. O Postgres **não** roda na VPS: use um projeto [Supabase](https://supabase.com/dashboard) e as duas connection strings no `.env`.

Há um script que replica estes passos: `deploy/setup-vps.sh`.

Portas públicas: **22** (SSH), **80** e **443** (Caddy). API e frontend só na rede Docker; Redis também.

## 1. Requisitos na VPS

- Ubuntu 22.04 ou 24.04, acesso SSH com `sudo`
- Projeto Supabase com `DATABASE_URL` (pooler, porta 6543) e `DATABASE_URL_MIGRATIONS` (conexão direta, porta 5432)
- Chaves OpenAI, ElevenLabs, Higgsfield e S3/R2
- Firewall do provedor (Hetzner Cloud Firewall, Security Group, etc.) alinhado ao ufw: as mesmas portas precisam estar abertas lá também

Os DNS de `scenecraft.mazting.studio` e `api.mazting.studio` devem apontar para o IPv4 da VPS (Caddy emite o certificado Let's Encrypt).

## 2. Docker e Docker Compose

Na VPS, como root (`sudo -i` ou prefixe com `sudo`):

```bash
apt-get update
apt-get install -y ca-certificates curl gnupg git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker compose version
```

Para usar Docker sem root no dia a dia:

```bash
usermod -aG docker "$USER"
# saia do SSH e entre de novo
```

## 3. Firewall (ufw)

Libere só SSH e HTTP/HTTPS. **Faça isso com a sessão SSH ainda aberta** e confirme que a 22 está permitida antes de ativar.

```bash
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 22/tcp comment 'ssh'
ufw allow 80/tcp comment 'caddy http'
ufw allow 443/tcp comment 'caddy https'
ufw enable
ufw status verbose
```

Não abra `3000`, `8000`, `6379` (Redis) nem `5432` (Postgres do Supabase). API, frontend e Redis só existem na rede interna do Compose.

## 4. Clonar o repositório

```bash
sudo mkdir -p /opt
sudo git clone https://github.com/mathias-cn/scenecraft.git /opt/scenecraft
sudo chown -R "$USER:$USER" /opt/scenecraft
cd /opt/scenecraft
```

Repo privado: use SSH (`git@github.com:mathias-cn/scenecraft.git`) com uma chave na VPS.

## 5. Variáveis de ambiente de produção

```bash
cd /opt/scenecraft
cp .env.example .env
nano .env
```

Preencha as URIs do Supabase e as chaves. Em produção **não** use `localhost` nem IP:porta — o Caddy serve HTTPS nos domínios:

| Variável | Exemplo |
| --- | --- |
| `DATABASE_URL` | Pooler Supabase `:6543` com `sslmode=require` |
| `DATABASE_URL_MIGRATIONS` | Conexão direta Supabase `:5432` com `sslmode=require` |
| `REDIS_URL` | Deixe `redis://redis:6379/0` (hostname do serviço Compose) |
| `CORS_ORIGINS` | `https://scenecraft.mazting.studio` (várias origens: separado por vírgula) |
| `NEXT_PUBLIC_API_URL` | `https://api.mazting.studio` |
| `BETTER_AUTH_SECRET` | Secret do Better Auth (`openssl rand -base64 32`) |
| `BETTER_AUTH_URL` | `https://scenecraft.mazting.studio` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Cliente OAuth 2.0 no Google Cloud Console |
| `OWNER_EMAIL` | Único email autorizado a entrar |
| `BETTER_AUTH_JWKS_URL` | `http://frontend:3000/api/auth/jwks` (HTTP interno na rede Docker; não use o domínio público) |

No Google Cloud Console, a redirect URI autorizada deve ser `https://scenecraft.mazting.studio/api/auth/callback/google`.

`NEXT_PUBLIC_API_URL` entra no **build** da imagem do frontend. Se mudar o domínio depois, reconstrua o serviço `frontend`.

O `.env` não vai para o git. Confira permissões:

```bash
chmod 600 .env
```

## 6. Migrations e subida

O serviço `api` em `docker-compose.prod.yml` roda `alembic upgrade head` no Supabase e depois o uvicorn (sem `--reload`). O worker só sobe depois que a API passar no healthcheck.

```bash
cd /opt/scenecraft
docker compose -f docker-compose.prod.yml up -d --build
```

Só as migrations, sem recriar tudo:

```bash
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

Conferir:

```bash
docker compose -f docker-compose.prod.yml ps
curl -fsS "https://api.mazting.studio/health"
curl -fsS -o /dev/null -w "%{http_code}\n" "https://scenecraft.mazting.studio"
```

No browser: `https://scenecraft.mazting.studio` (UI) e `https://api.mazting.studio/docs` (Swagger). Health interno, sem publicar portas:

```bash
docker compose -f docker-compose.prod.yml exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read())"
```

Logs:

```bash
docker compose -f docker-compose.prod.yml logs -f caddy api worker frontend
```

Parar:

```bash
docker compose -f docker-compose.prod.yml down
```

Atualizar o código:

```bash
cd /opt/scenecraft
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

O ingest de YouTube depende do **yt-dlp**. O YouTube trata downloaders como scrapers e muda as defesas com frequência (`nsig`, PO Token, TLS fingerprint, IP de VPS). Depois de um `poetry update yt-dlp` (ou se os logs mostrarem `nsig extraction failed` / `Requested format is not available` / `HTTP Error 403: Forbidden`), reconstrua **sem cache** para não reaproveitar a camada do pip. Um 403 com vídeo público não é link privado: é bloqueio anti-bot neste servidor — pode exigir outra cascata de `player_client`, impersonation (`curl-cffi`) ou PO Token, além da atualização mensal do yt-dlp.

```bash
docker compose -f docker-compose.prod.yml build --no-cache api worker
docker compose -f docker-compose.prod.yml up -d api worker
```

## 7. Atalho: script

Com Ubuntu já acessível via SSH:

```bash
# instala Docker, ufw, clona em /opt/scenecraft se preciso, cria .env e para para você editar
sudo bash -c 'git clone https://github.com/mathias-cn/scenecraft.git /opt/scenecraft && bash /opt/scenecraft/deploy/setup-vps.sh'
```

Na segunda execução, depois do `.env` preenchido, o mesmo script sobe o Compose. Ou, já dentro do clone:

```bash
cd /opt/scenecraft
sudo bash deploy/setup-vps.sh
```

Variáveis: `REPO_URL`, `APP_DIR`, `SKIP_FIREWALL=1`, `SKIP_CLONE=1`, `SKIP_UP=1`.

## Serviços no `docker-compose.prod.yml`

| Serviço | Papel | Publicado na VPS |
| --- | --- | --- |
| `caddy` | Reverse proxy HTTPS (Let's Encrypt) | `80`, `443` |
| `api` | FastAPI + Alembic na subida | não (`api:8000` interno) |
| `frontend` | Next.js (`next start`) | não (`frontend:3000` interno) |
| `worker` | Celery (um processo por fila) | não |
| `redis` | Broker / resultados | não |

Não há serviço `postgres`.
