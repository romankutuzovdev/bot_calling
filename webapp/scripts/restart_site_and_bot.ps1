# List relevant services/ports and restart CRM site + bot calling.
# Run in elevated PowerShell on the Windows Server.

param(
  [int]$BotPort = 8081,
  [string]$BotRoot = "C:\bot_calling",
  [switch]$BotOn8080
)

$ErrorActionPreference = "Continue"
if ($BotOn8080) { $BotPort = 8080 }

Write-Host "======== LISTENING PORTS ========" -ForegroundColor Cyan
netstat -ano | findstr ":80 "
netstat -ano | findstr ":443 "
netstat -ano | findstr ":8080"
netstat -ano | findstr ":8081"
netstat -ano | findstr ":8000"

Write-Host "`n======== WINDOWS SERVICES (MG / Caddy / bot) ========" -ForegroundColor Cyan
Get-Service | Where-Object {
  $_.Name -match 'MG|Caddy|bot|uvicorn|copart|crm' -or
  $_.DisplayName -match 'MG|Caddy|CRM|Bot|Copart'
} | Format-Table Name, Status, StartType, DisplayName -AutoSize

Write-Host "`n======== PYTHON / UVICORN / CADDY PROCESSES ========" -ForegroundColor Cyan
Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -match 'python|uvicorn|caddy|nginx' -or
    ($_.CommandLine -and $_.CommandLine -match 'uvicorn|webapp\.app|MG-CRM|caddy')
  } |
  Select-Object ProcessId, Name, @{n='Cmd';e={ if ($_.CommandLine) { $_.CommandLine.Substring(0, [Math]::Min(140, $_.CommandLine.Length)) } }} |
  Format-Table -AutoSize -Wrap

Write-Host "`n======== RESTART CRM SERVICES ========" -ForegroundColor Cyan
foreach ($svc in @('MG-CRM', 'MG-CRM-Caddy', 'Caddy', 'caddy')) {
  $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
  if ($s) {
    Write-Host "Restarting $($s.Name) ($($s.Status))..."
    try {
      Restart-Service -Name $s.Name -Force -ErrorAction Stop
      Write-Host "  OK: $($s.Name)" -ForegroundColor Green
    } catch {
      Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Yellow
      try {
        Stop-Service -Name $s.Name -Force -ErrorAction SilentlyContinue
        Start-Sleep 2
        Start-Service -Name $s.Name
        Write-Host "  OK after stop/start: $($s.Name)" -ForegroundColor Green
      } catch {
        Write-Host "  Still FAIL: $($_.Exception.Message)" -ForegroundColor Red
      }
    }
  }
}

Start-Sleep 2

Write-Host "`n======== RESTART BOT on 0.0.0.0:$BotPort ========" -ForegroundColor Cyan
# free bot port
try {
  $conns = Get-NetTCPConnection -LocalPort $BotPort -State Listen -ErrorAction SilentlyContinue
  if ($conns) {
    $conns | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
      Write-Host "Stop PID $_ on port $BotPort"
      Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep 2
  }
} catch {}

$py = Join-Path $BotRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "No python at $py" }

$logDir = Join-Path $BotRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$env:PYTHONPATH = $BotRoot
$env:COQUI_TOS_AGREED = "1"

Start-Process -FilePath $py `
  -ArgumentList @("-m", "uvicorn", "webapp.app:app", "--host", "0.0.0.0", "--port", "$BotPort") `
  -WorkingDirectory $BotRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $logDir "uvicorn.out.log") `
  -RedirectStandardError (Join-Path $logDir "uvicorn.err.log")

Start-Sleep 2

Write-Host "`n======== HEALTH CHECKS ========" -ForegroundColor Cyan
foreach ($url in @(
  "http://127.0.0.1:8080/",
  "http://127.0.0.1:$BotPort/",
  "http://127.0.0.1:8080/api/health",
  "http://127.0.0.1:$BotPort/api/elevenlabs/ping"
)) {
  try {
    $r = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 5
    Write-Host "OK  $($r.StatusCode) $url" -ForegroundColor Green
  } catch {
    Write-Host "FAIL $url  $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

Write-Host "`nBot URL (LAN): http://192.168.0.115:$BotPort/"
Write-Host "If CRM needs 8080, keep bot on 8081 (default). Use -BotOn8080 only if CRM is off."
