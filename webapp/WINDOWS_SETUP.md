# Установка на Windows Server (XTTS на CPU сервера)

Голос-клон и синтез идут **на Windows Server**, не на вашем Mac.
Mac нужен только чтобы скопировать проект (и при желании WAV-сэмпл).

## 1. Что нужно на сервере

- Windows Server (или Windows 10/11)
- Python 3.11 или 3.12
- Интернет (первый раз скачает модели)
- 16+ ГБ RAM желательно
- Браузер Chrome/Edge

## 2. Копирование

Скопируйте папку `bot_calling` на сервер, например в `C:\bot_calling`.

Если уже есть запись голоса с Mac — скопируйте вместе:

`voices\my_voice_22k.wav`

## 3. Установка (один раз)

PowerShell **от администратора**:

```powershell
cd C:\bot_calling
Set-ExecutionPolicy -Scope Process Bypass
.\webapp\scripts\install_windows.ps1
```

Скрипт поставит:

- веб (порт 8080)
- Ollama-модель `qwen2.5:3b`
- **PyTorch CPU** + **XTTS** (без NVIDIA)

## 4. Сэмпл голоса

Нужен файл `C:\bot_calling\voices\my_voice_22k.wav` (15–30 сек речи).

- скопировать с Mac, **или**
- записать на сервере:

```powershell
cd C:\bot_calling
.\.venv\Scripts\Activate.ps1
python -m src.record_voice
```

## 5. Запуск

```powershell
cd C:\bot_calling
.\webapp\scripts\start_windows.ps1
```

Открыть: `http://IP_СЕРВЕРА:8080`

В интерфейсе слева должно быть: **XTTS — клон вашего голоса**.

Первый ответ: модель грузится в RAM (минуты). Дальше каждая фраза на CPU — десятки секунд (на мощном сервере быстрее).

## 6. Firewall

```powershell
New-NetFirewallRule -DisplayName "Bot Calling 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
```

## 7. Если нужно быстро без ожидания

В UI переключите на **Microsoft Edge Neural** — скрипт тестается мгновенно, голос не ваш.

## Проблемы

| Симптом | Что сделать |
|---------|-------------|
| Нет сэмпла | `voices\my_voice_22k.wav` или `python -m src.record_voice` |
| Долго молчит | Норма для CPU; смотрите консоль `start_windows.ps1` |
| CUDA / GPU ошибки | Скрипт ставит CPU-torch; `CUDA_VISIBLE_DEVICES=` уже в start |
| Ollama bad | Запустите Ollama app, `ollama pull qwen2.5:3b` |
