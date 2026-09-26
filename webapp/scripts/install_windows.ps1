# Install on Windows Server (CPU). ASCII-only for Windows PowerShell 5.1.
#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Find-Ollama {
  $cmd = Get-Command ollama -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $candidates = @(
    "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "$env:ProgramFiles\Ollama\ollama.exe",
    "${env:ProgramFiles(x86)}\Ollama\ollama.exe"
  )
  foreach ($p in $candidates) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

Write-Host "==> Python check" -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) { throw "Python not found. Install Python 3.11+ with Add to PATH." }

Write-Host "==> Ollama" -ForegroundColor Cyan
$ollama = Find-Ollama
if (-not $ollama) {
  Write-Host "Ollama.exe not found. Install from https://ollama.com/download/windows" -ForegroundColor Yellow
  Write-Host "Then open a NEW PowerShell and re-run this script." -ForegroundColor Yellow
  Start-Process "https://ollama.com/download/windows"
  exit 1
}
Write-Host "Using: $ollama"
& $ollama pull qwen2.5:3b

Write-Host "==> venv" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) {
  python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

Write-Host "==> Web deps (fastapi, edge-tts)" -ForegroundColor Cyan
pip install -r webapp\requirements-web.txt

Write-Host "==> PyTorch CPU + XTTS (large download, wait)" -ForegroundColor Cyan
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r webapp\requirements-xtts-cpu.txt

$env:COQUI_TOS_AGREED = "1"
$env:CUDA_VISIBLE_DEVICES = ""

Write-Host "==> Voice sample check" -ForegroundColor Cyan
$wav = "voices\my_voice_22k.wav"
if (-not (Test-Path $wav)) {
  if (Test-Path "voices\my_voice.wav") {
    Write-Host "Found my_voice.wav - rename/copy to my_voice_22k.wav" -ForegroundColor Yellow
  } else {
    Write-Host "Missing $wav" -ForegroundColor Yellow
    Write-Host "Copy WAV from Mac to voices\my_voice_22k.wav"
    Write-Host "Or record: python -m src.record_voice"
  }
} else {
  Write-Host "Sample OK: $wav" -ForegroundColor Green
}

Write-Host ""
Write-Host "DONE. Start the app:" -ForegroundColor Green
Write-Host "  .\webapp\scripts\start_windows.ps1"
Write-Host "Open: http://127.0.0.1:8080"
Write-Host "Voice engine: XTTS clone on this server CPU"
