# Start web app on Windows Server. ASCII-only for PowerShell 5.1.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
  Write-Host "Run install_windows.ps1 first" -ForegroundColor Red
  exit 1
}

& .\.venv\Scripts\Activate.ps1

$env:PYTHONPATH = $Root
$env:COQUI_TOS_AGREED = "1"
$env:CUDA_VISIBLE_DEVICES = ""
$env:TORCH_DEVICE = "cpu"

try {
  Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 | Out-Null
} catch {
  Write-Host "Ollama not responding on :11434. Start Ollama app." -ForegroundColor Yellow
}

Write-Host "Starting http://0.0.0.0:8080 (XTTS on CPU)" -ForegroundColor Cyan
python -m uvicorn webapp.app:app --host 0.0.0.0 --port 8080
