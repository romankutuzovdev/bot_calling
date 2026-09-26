# Free port 8080 (stop whatever holds it, e.g. CRM) and start the bot.
# ASCII-only for Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
$Port = 8080
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> Looking for process on port $Port ..." -ForegroundColor Cyan

$pids = @()
try {
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($conns) {
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
  }
} catch {
  # Fallback via netstat (older Windows)
  $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
  foreach ($line in $lines) {
    $parts = ($line.ToString() -split '\s+') | Where-Object { $_ -ne '' }
    if ($parts.Count -ge 5) {
      $pids += [int]$parts[-1]
    }
  }
  $pids = $pids | Select-Object -Unique
}

if ($pids.Count -eq 0) {
  Write-Host "Port $Port is free." -ForegroundColor Green
} else {
  foreach ($procId in $pids) {
    try {
      $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
      $name = if ($p) { $p.ProcessName } else { "?" }
      Write-Host "Stopping PID $procId ($name) on port $Port ..." -ForegroundColor Yellow
      Stop-Process -Id $procId -Force -ErrorAction Stop
    } catch {
      Write-Host "Could not stop PID $procId : $_" -ForegroundColor Red
      Write-Host "Run PowerShell as Administrator and retry." -ForegroundColor Red
      exit 1
    }
  }
  Start-Sleep -Seconds 2
  Write-Host "Port $Port freed." -ForegroundColor Green
}

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
  Write-Host "No .venv - run .\webapp\scripts\install_windows.ps1 first" -ForegroundColor Red
  exit 1
}

& .\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = $Root
$env:COQUI_TOS_AGREED = "1"
$env:CUDA_VISIBLE_DEVICES = ""
$env:TORCH_DEVICE = "cpu"

Write-Host "Starting bot on http://0.0.0.0:$Port ..." -ForegroundColor Cyan
python -m uvicorn webapp.app:app --host 0.0.0.0 --port $Port
