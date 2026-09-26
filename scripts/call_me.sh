#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="$ROOT/.tmp/bin:$HOME/.local/bin:$PATH"
export COQUI_TOS_AGREED=1

# shellcheck disable=SC1091
source .venv/bin/activate

MODE="voice"
CONFIG="config_auto.yaml"

for arg in "$@"; do
  case "$arg" in
    ""|"#"*) ;;
    voice|text) MODE="$arg" ;;
    *.yaml|*.yml) CONFIG="$arg" ;;
  esac
done

if [[ ! -f "$CONFIG" ]]; then
  echo "Нет конфига: $CONFIG"
  echo "Запуск: ./scripts/call_me.sh"
  echo "   или: ./scripts/call_me.sh text"
  exit 1
fi

clear 2>/dev/null || true
cat <<EOF
╔══════════════════════════════════════════════╗
║  📞  Входящий: АвтоКит Импорт                ║
║  Максим · машинокомплекты США / Англия       ║
║  Голос: Microsoft Edge TTS                   ║
╚══════════════════════════════════════════════╝

  Режим: $MODE
  Говорите после фразы бота.
  Пауза ~1 сек = конец вашей реплики.
  Ctrl+C = положить трубку.

EOF

exec python -m src.main --mode "$MODE" --config "$CONFIG"
