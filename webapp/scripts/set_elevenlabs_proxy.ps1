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

$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($envFile, $out.ToArray(), $utf8)
Write-Host "OK: ELEVENLABS_PROXY saved to $envFile"
$hostHint = if ($Proxy -match '@') { ($Proxy.Split('@')[-1]) } else { $Proxy }
Write-Host "proxy host: $hostHint"

$keyLine = $out | Where-Object { $_ -match '^\s*ELEVENLABS_API_KEY\s*=' } | Select-Object -First 1
$key = $null
if ($keyLine) { $key = ($keyLine -split '=', 2)[1].Trim().Trim('"').Trim("'") }

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "Testing via httpx (PowerShell -Proxy often returns 407 without creds)..."
& $py -c @"
import asyncio, httpx
proxy = r'''$Proxy'''
key = r'''$key'''
print('proxy host:', proxy.split('@')[-1] if '@' in proxy else proxy)
async def main():
    async with httpx.AsyncClient(proxy=proxy, timeout=45.0, follow_redirects=False) as c:
        r = await c.get(
            'https://api.elevenlabs.io/v1/voices',
            headers={'xi-api-key': key, 'Accept': 'application/json'},
        )
    print('status', r.status_code, 'bytes', len(r.content or b''))
    print((r.content or b'')[:220])
asyncio.run(main())
"@

Write-Host ""
Write-Host "Next: .\webapp\scripts\deploy_update.ps1"
Write-Host "Then: Invoke-RestMethod http://127.0.0.1:8080/api/elevenlabs/ping"
