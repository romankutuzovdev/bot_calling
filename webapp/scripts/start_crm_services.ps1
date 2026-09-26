# Start MG-CRM + Caddy and show why they fail. Run as Administrator.

$ErrorActionPreference = "Continue"

Write-Host "==> Current status" -ForegroundColor Cyan
Get-Service MG-CRM, MG-CRM-Caddy -ErrorAction SilentlyContinue |
  Format-Table Name, Status, StartType -AutoSize

foreach ($name in @("MG-CRM", "MG-CRM-Caddy")) {
  $s = Get-Service -Name $name -ErrorAction SilentlyContinue
  if (-not $s) {
    Write-Host "MISSING service: $name" -ForegroundColor Red
    continue
  }
  Write-Host "`n==> Starting $name ..." -ForegroundColor Cyan
  try {
    Set-Service -Name $name -StartupType Automatic -ErrorAction SilentlyContinue
    Start-Service -Name $name -ErrorAction Stop
    Write-Host "OK: $name is $((Get-Service $name).Status)" -ForegroundColor Green
  } catch {
    Write-Host "FAIL Start-Service $name : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Recent System log:" -ForegroundColor Yellow
    Get-WinEvent -FilterHashtable @{
      LogName = "System"
      ProviderName = "Service Control Manager"
      StartTime = (Get-Date).AddMinutes(-30)
    } -MaxEvents 40 -ErrorAction SilentlyContinue |
      Where-Object { $_.Message -match $name } |
      Select-Object -First 5 TimeCreated, Id, Message |
      Format-List
  }
}

Write-Host "`n==> Service config (paths)" -ForegroundColor Cyan
foreach ($name in @("MG-CRM", "MG-CRM-Caddy")) {
  $cfg = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction SilentlyContinue
  if ($cfg) {
    Write-Host "$($cfg.Name) | $($cfg.State) | $($cfg.StartMode)"
    Write-Host "  Path: $($cfg.PathName)"
  }
}

Write-Host "`n==> Ports after start" -ForegroundColor Cyan
netstat -ano | findstr ":443 "
netstat -ano | findstr ":8080"
netstat -ano | findstr ":8081"

Write-Host "`n==> HTTP checks" -ForegroundColor Cyan
foreach ($url in @("http://127.0.0.1:8080/", "http://127.0.0.1:8081/")) {
  try {
    $r = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 8
    Write-Host "OK $($r.StatusCode) $url" -ForegroundColor Green
  } catch {
    Write-Host "FAIL $url :: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}
