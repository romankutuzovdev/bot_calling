#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="$ROOT/.tmp/bin:$HOME/.local/bin:$PATH"
export COQUI_TOS_AGREED=1

# shellcheck disable=SC1091
source .venv/bin/activate

MODE="voice"
CONFIG="config_multiglobal.yaml"

for arg in "$@"; do
  case "$arg" in
    ""|"#"*) ;;
    voice|text) MODE="$arg" ;;
    *.yaml|*.yml) CONFIG="$arg" ;;
  esac
done

if [[ ! -f "$CONFIG" ]]; then
  echo "Нет конфига: $CONFIG"
  echo "Запуск: ./scripts/call_multiglobal.sh"
  echo "   или: ./scripts/call_multiglobal.sh text"
  exit 1
fi

clear 2>/dev/null || true
cat <<EOF
╔══════════════════════════════════════════════════╗
║  📞  Холодный обзвон: МультиГлобал Групп         ║
║  Александра · логистика                          ║
║  Цель: потребность → контакт менеджеру           ║
║  Голос: Microsoft Edge TTS                       ║
╚══════════════════════════════════════════════════╝

  Скрипт:
  1. Представление → удобно минуту?
  2. ЛПР по логистике?
  3. Сторонние перевозчики / направления / частота
  4. Презентация → WhatsApp / Telegram / почта

  Говорите — слова появятся на экране сразу.
  Профиль голоса подстроит тон диалога.
  Пауза ~1 сек = конец реплики.
  Ctrl+C = положить трубку.

EOF

exec python -m src.main --mode "$MODE" --config "$CONFIG"
