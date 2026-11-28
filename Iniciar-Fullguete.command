#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
root="$PWD"
state="$root/.fullguete-local"
api_host="${FULLGUETE_API_HOST:-127.0.0.1}"
frontend_url="http://127.0.0.1:3001"
api_url="http://$api_host:8001"
open_browser=true
case "${1:-}" in
  "") ;;
  --no-open) open_browser=false ;;
  *) printf 'Uso: %s [--no-open]\n' "$0" >&2; exit 2 ;;
esac

unset PYTHONPATH PYTHONHOME
command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3,11))' || {
  printf 'Instale o Python 3.11 ou superior.\n' >&2; exit 1;
}
# Verifica os endereços antes de criar arquivos, instalar pacotes ou iniciar serviços.
FULLGUETE_API_HOST="$api_host" python3 -m portal_api.local --check
command -v node >/dev/null && command -v npm >/dev/null && node -e '
  const [major, minor] = process.versions.node.split(".").map(Number);
  process.exit(major < 20 || (major === 20 && minor < 9) ? 1 : 0);
' || { printf 'Instale o Node.js 20.9 ou superior com npm.\n' >&2; exit 1; }
command -v curl >/dev/null || { printf 'Instale o curl.\n' >&2; exit 1; }

for local_path in "$state" "$state/venv" "$state/homologacao" "$state/homologacao/homologacao.db"; do
  if [[ -L "$local_path" ]]; then
    printf 'Caminho local do Fullguete é um link simbólico: %s\n' "$local_path" >&2
    exit 1
  fi
done
umask 077
mkdir -p "$state"
if ! mkdir "$state/starting"; then
  printf 'Já existe uma inicialização neste clone.\n' >&2
  exit 1
fi
api_pid=""
frontend_pid=""
cleanup() {
  trap - EXIT
  if [[ -n "$frontend_pid" ]]; then
    kill "$frontend_pid" 2>/dev/null || true
    wait "$frontend_pid" 2>/dev/null || true
  fi
  if [[ -n "$api_pid" ]]; then
    kill "$api_pid" 2>/dev/null || true
    wait "$api_pid" 2>/dev/null || true
  fi
  rmdir "$state/starting" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

python="$state/venv/bin/python"
if [[ ! -x "$python" ]]; then
  python3 -m venv "$state/venv"
  rm -f "$state/python-deps"
fi

install_if_changed() {
  local fingerprint="$1" cache="$2"
  shift 2
  if [[ ! -f "$cache" || "$(< "$cache")" != "$fingerprint" ]]; then
    "$@"
    printf '%s\n' "$fingerprint" > "$cache"
  fi
}

install_if_changed "$(cksum requirements.txt portal_api/requirements.txt)" "$state/python-deps" \
  "$python" -m pip install -r requirements.txt -r portal_api/requirements.txt

# Usa apenas o ambiente fictício do Fullguete. A preparação recebe o próprio
# diretório e o processo da API não usa caminho de banco ou chave herdados.
unset GEMINI_API_KEY CNPJ_WS_TOKEN CNPJA_API_KEY LOCALIZA_CNPJ_TOKEN
export PYTHON_DOTENV_DISABLED=1 FULLGUETE_LOCAL_ENV_ONLY=1 FULLGUETE_MODO=simulado
export FULLGUETE_DB_PATH="$state/streamlit-inativo.db"
export FULLGUETE_MODELOS_DIR="$state/modelos-streamlit-inativo"
export FULLGUETE_API_DB_COPY="$state/homologacao/homologacao.db"
export FULLGUETE_API_WRITE_MODE=homologacao FULLGUETE_API_HOST="$api_host"
export FULLGUETE_API_ORIGIN="$api_url" FULLGUETE_API_CNPJA_KEY=""
export NO_PROXY="127.0.0.1,127.0.0.2,localhost"
if [[ ! -f "$FULLGUETE_API_DB_COPY" ]]; then
  "$python" -m portal_api.sandbox "$state/homologacao"
fi

cd "$root/frontend"
if [[ ! -f node_modules/next/dist/bin/next ]]; then rm -f "$state/node-deps"; fi
install_if_changed "$(cksum package-lock.json)" "$state/node-deps" npm ci
npm run build
cd "$root"
"$python" -m portal_api.local --check

"$python" -m portal_api.local &
api_pid=$!

wait_http() {
  local url="$1" pid="$2" attempt
  for ((attempt=0; attempt<40; attempt++)); do
    kill -0 "$pid" 2>/dev/null || break
    if curl --noproxy '*' --silent --fail --max-time 1 "$url" >/dev/null; then return 0; fi
    sleep 1
  done
  printf 'Fullguete não respondeu em %s. Veja a saída acima.\n' "$url" >&2
  return 1
}
wait_http "$api_url/v1/health" "$api_pid"

(
  cd "$root/frontend"
  exec node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3001
) &
frontend_pid=$!
wait_http "$frontend_url/operacao" "$frontend_pid"

printf '\nFullguete: %s/operacao\nAPI: %s\nUse Ctrl+C para encerrar os dois serviços.\n' "$frontend_url" "$api_url"
if [[ "$open_browser" == true && "$(uname -s)" == Darwin ]]; then
  open "$frontend_url/operacao" || printf 'Abra o endereço acima no navegador.\n'
fi
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1
done
printf 'Um serviço do Fullguete foi encerrado.\n' >&2
exit 1
