#Requires -RunAsAdministrator
<#
  Установка на Windows Server (CPU):
  - Ollama + веб на :8080
  - XTTS клон голоса на CPU (не на вашем Mac)
#>

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> Проверка Python 3.11/3.12" -ForegroundColor Cyan
python --version

Write-Host "==> Ollama" -ForegroundColor Cyan
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  Write-Host "Установите Ollama: https://ollama.com/download/windows" -ForegroundColor Yellow
  Start-Process "https://ollama.com/download/windows"
  exit 1
}
ollama pull qwen2.5:3b

Write-Host "==> venv" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) {
  python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

Write-Host "==> Веб (fastapi, edge-tts)" -ForegroundColor Cyan
pip install -r webapp\requirements-web.txt

Write-Host "==> PyTorch CPU (без CUDA) + XTTS" -ForegroundColor Cyan
Write-Host "Это долго: скачивается torch CPU + coqui-tts (несколько ГБ)…"
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r webapp\requirements-xtts-cpu.txt

# Согласие Coqui / только CPU
$env:COQUI_TOS_AGREED = "1"
$env:CUDA_VISIBLE_DEVICES = ""

Write-Host "==> Проверка сэмпла голоса" -ForegroundColor Cyan
$wav = "voices\my_voice_22k.wav"
if (-not (Test-Path $wav)) {
  if (Test-Path "voices\my_voice.wav") {
    Write-Host "Есть my_voice.wav — скопируйте/переименуйте в my_voice_22k.wav или запишите заново."
  } else {
    Write-Host "Нет $wav" -ForegroundColor Yellow
    Write-Host "Вариант A: скопируйте WAV с Mac (voices\my_voice_22k.wav) на сервер"
    Write-Host "Вариант B: запись на сервере с микрофоном:"
    Write-Host "  python -m src.record_voice"
  }
} else {
  Write-Host "Сэмпл найден: $wav" -ForegroundColor Green
}

Write-Host ""
Write-Host "Готово. Запуск на ЭТОМ Windows-сервере:" -ForegroundColor Green
Write-Host "  .\webapp\scripts\start_windows.ps1"
Write-Host "Откройте http://IP_СЕРВЕРА:8080"
Write-Host "Движок голоса: XTTS (клон) — работает на CPU сервера."
