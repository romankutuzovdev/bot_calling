# Open inbound TCP 8080 for Bot Calling (Windows Firewall).
# Run in elevated PowerShell: Right-click -> Run as Administrator

param(
  [int]$Port = 8080,
  [string]$PythonExe = "C:\bot_calling\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Continue"

Write-Host "==> Remove old Bot Calling rules" -ForegroundColor Cyan
Get-NetFirewallRule -DisplayName "Bot Calling*" -ErrorAction SilentlyContinue |
  Remove-NetFirewallRule -ErrorAction SilentlyContinue

Write-Host "==> Allow TCP port $Port (all profiles)" -ForegroundColor Cyan
New-NetFirewallRule `
  -DisplayName "Bot Calling $Port TCP In" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort $Port `
  -Profile Any `
  -EdgeTraversalPolicy Allow `
  -Enabled True | Out-Null

if (Test-Path $PythonExe) {
  Write-Host "==> Allow python.exe inbound" -ForegroundColor Cyan
  New-NetFirewallRule `
    -DisplayName "Bot Calling Python In" `
    -Direction Inbound `
    -Action Allow `
    -Program $PythonExe `
    -Profile Any `
    -EdgeTraversalPolicy Allow `
    -Enabled True | Out-Null
}

Write-Host "==> Current rules" -ForegroundColor Cyan
Get-NetFirewallRule -DisplayName "Bot Calling*" |
  Format-Table DisplayName, Enabled, Direction, Action, Profile, EdgeTraversalPolicy -AutoSize

Write-Host "==> Local check" -ForegroundColor Cyan
try {
  (Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 5).StatusCode
} catch {
  Write-Host "Local fail: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "DONE. Test from phone LTE: http://YOUR_PUBLIC_IP:$Port/"
Write-Host "If still timeout - not Windows Firewall, fix router/A1 port forward."
Write-Host ""
Write-Host "Optional TEMP test (disable firewall 60s) - run as Admin:"
Write-Host "  Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False"
Write-Host "  Start-Sleep 60"
Write-Host "  Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True"
