# Write ELEVENLABS_PROXY into C:\bot_calling\.env and test API.
# Examples:
#   .\webapp\scripts\set_elevenlabs_proxy.ps1 -Proxy "http://user:pass@1.2.3.4:8080"
#   .\webapp\scripts\set_elevenlabs_proxy.ps1 -Proxy "socks5://user:pass@1.2.3.4:1080"

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
$out = New-Object System.Collections.Generic.List[string]
foreach ($line in $lines) {
    if ($line -match '^\s*ELEVENLABS_PROXY\s*=') {
        $found = $true
        [void]$out.Add("ELEVENLABS_PROXY=$Proxy")
    } else {
        [void]$out.Add($line)
    }
}
if (-not $found) {
    [void]$out.Add("ELEVENLABS_PROXY=$Proxy")
}

# UTF-8 without BOM (PS 5.1 Set-Content -Encoding UTF8 adds BOM and breaks keys)
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($envFile, $out.ToArray(), $utf8)
Write-Host "OK: ELEVENLABS_PROXY saved to $envFile"
Write-Host "File contents:"
Get-Content $envFile | ForEach-Object {
    if ($_ -match 'ELEVENLABS_API_KEY=') { "ELEVENLABS_API_KEY=***" }
    elseif ($_ -match 'ELEVENLABS_PROXY=') {
        $p = ($_ -split '=', 2)[1]
        if ($p -match '@') { "ELEVENLABS_PROXY=***@" + ($p.Split('@')[-1]) } else { "ELEVENLABS_PROXY=$p" }
    } else { $_ }
}

$keyLine = $out | Where-Object { $_ -match '^\s*ELEVENLABS_API_KEY\s*=' } | Select-Object -First 1
$key = $null
if ($keyLine) { $key = ($keyLine -split '=', 2)[1].Trim().Trim('"').Trim("'") }

Write-Host "Testing api.elevenlabs.io via proxy..."
$isSocks = $Proxy -match '^\s*socks5?://'
if ($isSocks) {
    Write-Host "SOCKS: skip PowerShell -Proxy test. Restart bot, check /api/elevenlabs/ping"
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
        Write-Host "502/timeout = bad proxy. Try socks5:// or another provider."
    }
}

Write-Host ""
Write-Host "Next: .\webapp\scripts\deploy_update.ps1"
Write-Host "Then: Invoke-RestMethod http://127.0.0.1:8080/api/elevenlabs/ping"
