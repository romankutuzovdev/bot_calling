#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 1/4 Python venv"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "==> 2/4 Проверка Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama не найден."
  echo "Скачайте установщик: https://ollama.com/download"
  echo "После установки запустите этот скрипт снова."
  exit 1
fi

echo "==> 3/4 Запуск Ollama (если ещё не запущен)"
if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Стартую ollama serve в фоне..."
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  sleep 2
fi

MODEL="$(python - <<'PY'
import yaml
print(yaml.safe_load(open("config.yaml"))["ollama"]["model"])
PY
)"

echo "==> 4/4 Модель: $MODEL"
ollama pull "$MODEL"

echo
echo "Готово. Запуск:"
echo "  source .venv/bin/activate"
echo "  python -m src.main --mode text   # быстрый тест без микрофона"
echo "  python -m src.main --mode voice  # голос"
