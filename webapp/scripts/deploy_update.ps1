# Update from GitHub and restart bot on Windows Server.
# Used by GitHub Actions self-hosted runner OR Task Scheduler.
# ASCII-only for Windows PowerShell 5.1.

param(
  [string]$RepoRoot = "C:\bot_calling",
  [int]$Port = 8080,
  [switch]$SkipPip
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

Write-Host "==> git pull" -ForegroundColor Cyan
git fetch origin
git checkout main
git reset --hard origin/main

# Prefer project .venv, fallback to webapp\.venv
$py = $null
foreach ($cand in @(
  "$RepoRoot\.venv\Scripts\python.exe",
  "$RepoRoot\webapp\.venv\Scripts\python.exe"
)) {
  if (Test-Path $cand) { $py = $cand; break }
}
if (-not $py) {
  throw "No venv python found. Run install_windows.ps1 once."
}
Write-Host "Python: $py"

if (-not $SkipPip) {
  Write-Host "==> pip (web deps)" -ForegroundColor Cyan
  & $py -m pip install -q -r "$RepoRoot\webapp\requirements-web.txt"
  & $py -m pip install -q edge-tts
}

Write-Host "==> free port $Port" -ForegroundColor Cyan
try {
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($conns) {
    $conns | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
      Write-Host "Stop PID $_"
      Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
  }
} catch {
  $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
  foreach ($line in $lines) {
    $parts = ($line.ToString() -split '\s+') | Where-Object { $_ -ne '' }
    if ($parts.Count -ge 5) {
      Stop-Process -Id ([int]$parts[-1]) -Force -ErrorAction SilentlyContinue
    }
  }
  Start-Sleep -Seconds 2
}

Write-Host "==> start uvicorn 0.0.0.0:$Port" -ForegroundColor Cyan
$env:PYTHONPATH = $RepoRoot
$env:COQUI_TOS_AGREED = "1"
$env:CUDA_VISIBLE_DEVICES = ""
$env:TORCH_DEVICE = "cpu"

$logDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "uvicorn.out.log"
$errLog = Join-Path $logDir "uvicorn.err.log"

Start-Process -FilePath $py `
  -ArgumentList @("-m", "uvicorn", "webapp.app:app", "--host", "0.0.0.0", "--port", "$Port") `
  -WorkingDirectory $RepoRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $outLog `
  -RedirectStandardError $errLog

Start-Sleep -Seconds 2
Write-Host "DONE. Open http://0.0.0.0:$Port (or server IP:$Port)" -ForegroundColor Green
Write-Host "Logs: $outLog"
