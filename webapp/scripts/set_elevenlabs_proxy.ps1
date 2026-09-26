# Write ELEVENLABS_PROXY into C:\bot_calling\.env and test API.
# Examples:
#   .\webapp\scripts\set_elevenlabs_proxy.ps1 -Proxy "http://user:pass@1.2.3.4:8080"
#   .\webapp\scripts\set_elevenlabs_proxy.ps1 -Proxy "socks5://127.0.0.1:1080"

param(
    [Parameter(Mandatory = $true)]
    [string]$Proxy,

    [string]$Root = "C:\bot_calling"
)

$ErrorActionPreference = "Stop"
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    New-Item -ItemType File -Path $envFile -Force | Out-Null
}

$lines = @(Get-Content $envFile -ErrorAction SilentlyContinue)
$found = $false
$out = foreach ($line in $lines) {
    if ($line -match '^\s*ELEVENLABS_PROXY\s*=') {
        $found = $true
        "ELEVENLABS_PROXY=$Proxy"
    } else {
        $line
    }
}
if (-not $found) {
    $out += "ELEVENLABS_PROXY=$Proxy"
}
$out | Set-Content -Path $envFile -Encoding UTF8
Write-Host "OK: ELEVENLABS_PROXY saved to $envFile"

$keyLine = $out | Where-Object { $_ -match '^\s*ELEVENLABS_API_KEY\s*=' } | Select-Object -First 1
$key = $null
if ($keyLine) { $key = ($keyLine -split '=', 2)[1].Trim().Trim('"').Trim("'") }

Write-Host "Testing api.elevenlabs.io via proxy..."
$isSocks = $Proxy -match '^\s*socks5?://'
if ($isSocks) {
    Write-Host "SOCKS proxy: PowerShell -Proxy may not work. Restart bot and check /api/elevenlabs/ping"
} else {
    try {
        $headers = @{}
        if ($key) { $headers["xi-api-key"] = $key }
        $r = Invoke-WebRequest "https://api.elevenlabs.io/v1/voices" `
            -Proxy $Proxy `
            -Headers $headers `
            -UseBasicParsing `
            -TimeoutSec 30
        Write-Host "Status: $($r.StatusCode), bytes: $($r.RawContentLength)"
        if ($r.Content -match '^\s*<') {
            Write-Host "WARN: HTML response (geo-block?). Try another proxy/country."
        } elseif ($r.Content -match '"voices"') {
            Write-Host "OK: JSON voices list - proxy works."
        } else {
            Write-Host "Response is not HTML; check body manually."
        }
    } catch {
        Write-Host "Proxy request failed: $($_.Exception.Message)"
        Write-Host "If this is SOCKS5, ignore and test /api/elevenlabs/ping after bot restart."
    }
}

Write-Host ""
Write-Host "Next: restart bot (deploy_update.ps1) then open /api/elevenlabs/ping"
