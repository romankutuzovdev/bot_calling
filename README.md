# AI Sales Caller — локальный MVP

Голосовой бот-продавец на **бесплатном** стеке. Сейчас это **симулятор звонка** на Mac (микрофон ↔ колонки). Бесплатной реальной телефонии почти нет — её подключим позже.

## Стек

| Часть | Что | Деньги |
|------|-----|--------|
| LLM | [Ollama](https://ollama.com) + `qwen2.5:3b` на вашем ПК | бесплатно |
| STT | faster-whisper | бесплатно |
| TTS | Piper (локально, `ru_RU-denis-medium`) | бесплатно |
| Аудио | микрофон + `afplay` | бесплатно |

## Быстрый старт

### 1. Python (зависимости уже ставятся в `.venv`)

```bash
cd /Users/roman/Desktop/bot_calling
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Проверка пайплайна БЕЗ нейросети

Пока Ollama не установлена:

```bash
source .venv/bin/activate
python -m src.main --mode text --mock
```

### 3. Установите Ollama (локальная LLM)

1. Скачайте: https://ollama.com/download  
2. Перетащите в Программы и откройте приложение  
3. В терминале:

```bash
ollama pull qwen2.5:3b
python scripts/check_env.py
```

Либо после установки Ollama: `./scripts/setup_mac.sh`

### 4. Тест с локальной моделью

```bash
source .venv/bin/activate
python -m src.main --mode text    # печатаете ответы
python -m src.main --mode voice   # говорите в микрофон
```

В voice: говорите после «Слушаю…». Пауза ~1.2 сек завершает фразу.

## Голос (Piper + запись сэмпла)

Бот говорит **локально через Piper** (мужской Denis).

Записать ваш голос (~25 сек) для будущего клонирования:

```bash
source .venv/bin/activate
python -m src.record_voice
```

После записи нормализуйте для XTTS:

```bash
.tmp/bin/ffmpeg -y -i voices/my_voice.wav -ar 22050 -ac 1 voices/my_voice_22k.wav
```

Запуск бота **вашим голосом**:

```bash
source .venv/bin/activate
./scripts/call_me.sh
```

В `config_auto.yaml`: `tts.engine: clone`. Для быстрого Denis без клона — `engine: piper`.

## CI/CD (push → Windows Server)

Подробно: [webapp/CICD.md](webapp/CICD.md) — self-hosted GitHub Actions runner + `deploy_update.ps1`.

```bash
git push origin main
# сервер сам делает git pull и перезапускает бота на :8080
```

## Веб-тестер (порт 8080)

```bash
./webapp/scripts/start_web.sh
# http://127.0.0.1:8080
```

На Windows Server: `webapp/scripts/install_windows.ps1` → `start_windows.ps1`.  
Подробнее: [webapp/README.md](webapp/README.md).

## МультиГлобал Групп

```bash
./scripts/call_multiglobal.sh        # голос
./scripts/call_multiglobal.sh text   # текстом
```

Выясняет потребность: маршрут (РБ/СНГ/ЕС/Турция/Китай) → груз → объём → сроки → заявка на расчёт.
Конфиг: `config_multiglobal.yaml`.

## Логистика — выяснение потребности

```bash
./scripts/call_logistics.sh          # голос
./scripts/call_logistics.sh text     # текстом
```

Скрипт (`config_logistics.yaml`): есть ли перевозки → маршрут → груз/объём → сроки → заявка на расчёт.

Правьте `config.yaml`: название, цена, выгоды, голос, модель.

При **16+ ГБ RAM** лучше русский на:

```yaml
ollama:
  model: "qwen2.5:7b"
```

Затем: `ollama pull qwen2.5:7b`

## Как устроен «звонок»

1. Бот здоровается (как после ответа на трубку).
2. Вы отвечаете голосом или текстом.
3. Локальная LLM ведёт продажу по скрипту.
4. Конец: `CLOSE_DEAL` / `END_CALL` или лимит ходов.

## Следующий шаг

Телефония (Twilio / Voximplant) — платные минуты; промпт и Ollama остаются теми же.
