# Веб-тестер бота (порт 8080)

Интерфейс для проверки скрипта холодного обзвона + Ollama.

## Что умеет

- Редактор скрипта (что спрашивать)
- Тестовый «звонок» текстом и голосом (микрофон в Chrome/Edge)
- Профиль голоса (пол / эмоция / темп) и подстройка тона
- Работа с локальной Ollama (`qwen2.5:3b` бесплатно)

## Установка на Windows Server

Пошагово: [webapp/WINDOWS_SETUP.md](WINDOWS_SETUP.md)

XTTS (клон голоса) работает **на CPU Windows-сервера**, не на Mac.

```powershell
cd C:\bot_calling
.\webapp\scripts\install_windows.ps1
.\webapp\scripts\start_windows.ps1
```

Открыть: http://IP_СЕРВЕРА:8080

Сэмпл: `voices\my_voice_22k.wav` (скопировать с Mac или `python -m src.record_voice`).

## macOS / Linux (проверка)

```bash
cd bot_calling
source .venv/bin/activate
pip install -r webapp/requirements-web.txt
ollama pull qwen2.5:3b
chmod +x webapp/scripts/start_web.sh
./webapp/scripts/start_web.sh
```

## Как тестировать

1. Слева отредактируйте скрипт → **Сохранить скрипт**
2. Справа **Новый звонок**
3. Отвечайте текстом или кнопкой 🎤
4. Смотрите ответы бота и профиль голоса
