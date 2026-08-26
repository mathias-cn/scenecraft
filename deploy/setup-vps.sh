#!/usr/bin/env bash
# Bootstrap de uma VPS Ubuntu para o SceneCraft (Docker Compose de produção).
# Uso (na VPS, como root ou com sudo):
#   curl -fsSL https://raw.githubusercontent.com/mathias-cn/scenecraft/main/deploy/setup-vps.sh | sudo bash
#   # ou, já com o repo clonado:
#   sudo bash deploy/setup-vps.sh
#
# Variáveis opcionais:
#   REPO_URL   default: https://github.com/mathias-cn/scenecraft.git
#   APP_DIR    default: diretório do repo se o script estiver nele; senão /opt/scenecraft
#   SKIP_FIREWALL=1   não altera o ufw
#   SKIP_CLONE=1      não clona / não dá pull
#   SKIP_UP=1         instala Docker e o firewall, mas não sobe os containers

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/mathias-cn/scenecraft.git}"
SKIP_FIREWALL="${SKIP_FIREWALL:-0}"
SKIP_CLONE="${SKIP_CLONE:-0}"
SKIP_UP="${SKIP_UP:-0}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Rode como root: sudo bash $0" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_from_script="$(cd "${script_dir}/.." && pwd)"
if [[ -f "${repo_from_script}/docker-compose.prod.yml" ]]; then
  APP_DIR="${APP_DIR:-${repo_from_script}}"
else
  APP_DIR="${APP_DIR:-/opt/scenecraft}"
fi

echo "==> 1/5 Docker Engine + Compose v2"
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    >/etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  apt-get update -y
  apt-get install -y git
  echo "    Docker já instalado: $(docker --version)"
fi

systemctl enable --now docker
docker compose version

if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  usermod -aG docker "${SUDO_USER}" || true
  echo "    Usuário ${SUDO_USER} adicionado ao grupo docker (precisa relogar)."
fi

echo "==> 2/5 Firewall ufw (22, 3000, 8000)"
if [[ "${SKIP_FIREWALL}" != "1" ]]; then
  apt-get install -y ufw
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow OpenSSH
  ufw allow 22/tcp comment 'ssh'
  ufw allow 3000/tcp comment 'scenecraft frontend'
  ufw allow 8000/tcp comment 'scenecraft api'
  ufw --force enable
  ufw status verbose
else
  echo "    SKIP_FIREWALL=1 — ufw não foi alterado."
fi

echo "==> 3/5 Repositório em ${APP_DIR}"
if [[ "${SKIP_CLONE}" != "1" ]]; then
  mkdir -p "$(dirname "${APP_DIR}")"
  if [[ -d "${APP_DIR}/.git" ]]; then
    git -C "${APP_DIR}" pull --ff-only
  elif [[ -f "${APP_DIR}/docker-compose.prod.yml" ]]; then
    echo "    Repo já presente em ${APP_DIR}"
  else
    git clone "${REPO_URL}" "${APP_DIR}"
  fi
else
  echo "    SKIP_CLONE=1"
fi

if [[ ! -f "${APP_DIR}/docker-compose.prod.yml" ]]; then
  echo "docker-compose.prod.yml não encontrado em ${APP_DIR}" >&2
  exit 1
fi

cd "${APP_DIR}"

echo "==> 4/5 Arquivo .env de produção"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "    Criei .env a partir de .env.example. Edite antes de subir:"
  echo "      nano ${APP_DIR}/.env"
  echo "    Obrigatório: URIs do Supabase, chaves dos providers, CORS_ORIGINS e NEXT_PUBLIC_API_URL."
  echo "    Depois rode de novo: sudo bash ${APP_DIR}/deploy/setup-vps.sh"
  exit 0
fi

if grep -qE 'YOUR_PASSWORD|PROJECT_REF|your_openai_api_key_here|your_higgsfield_api_key_here' .env; then
  echo "    O .env ainda tem placeholders do .env.example. Edite ${APP_DIR}/.env e rode o script de novo." >&2
  exit 1
fi

if grep -qE '^NEXT_PUBLIC_API_URL=http://localhost' .env || grep -qE '^CORS_ORIGINS=http://localhost' .env; then
  echo "    Aviso: CORS_ORIGINS / NEXT_PUBLIC_API_URL ainda apontam para localhost."
  echo "    Em produção use o IP ou domínio da VPS (ex.: http://SEU_IP:3000 e http://SEU_IP:8000)."
fi

echo "==> 5/5 Migrations (Alembic no Supabase) + docker compose"
if [[ "${SKIP_UP}" == "1" ]]; then
  echo "    SKIP_UP=1 — containers não foram iniciados."
  echo "    Suba com: cd ${APP_DIR} && docker compose -f docker-compose.prod.yml up -d --build"
  exit 0
fi

docker compose -f docker-compose.prod.yml up -d --build

echo
echo "Pronto. A API aplica alembic upgrade head na subida."
echo "  Frontend: http://SEU_IP:3000"
echo "  API:      http://SEU_IP:8000/health"
echo "  Logs:     docker compose -f ${APP_DIR}/docker-compose.prod.yml logs -f api worker frontend"
echo
echo "Se o painel chamar a API no host errado, ajuste NEXT_PUBLIC_API_URL no .env e reconstrua o frontend:"
echo "  docker compose -f docker-compose.prod.yml up -d --build frontend"
