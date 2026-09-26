$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
  Write-Host "Сначала запустите install_windows.ps1" -ForegroundColor Red
  exit 1
}

& .\.venv\Scripts\Activate.ps1

# XTTS только на CPU этого Windows-сервера (не Mac)
$env:PYTHONPATH = $Root
$env:COQUI_TOS_AGREED = "1"
$env:CUDA_VISIBLE_DEVICES = ""
$env:TORCH_DEVICE = "cpu"

try {
  Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 | Out-Null
} catch {
  Write-Host "Ollama не отвечает на :11434. Запустите приложение Ollama." -ForegroundColor Yellow
}

Write-Host "Старт на http://0.0.0.0:8080 (XTTS = CPU Windows-сервера)" -ForegroundColor Cyan
python -m uvicorn webapp.app:app --host 0.0.0.0 --port 8080
