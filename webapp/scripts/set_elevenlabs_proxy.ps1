# Добавить/обновить ELEVENLABS_PROXY в C:\bot_calling\.env и проверить API.
# Пример:
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
Write-Host "OK: ELEVENLABS_PROXY записан в $envFile"

# ключ для теста
$keyLine = $out | Where-Object { $_ -match '^\s*ELEVENLABS_API_KEY\s*=' } | Select-Object -First 1
$key = $null
if ($keyLine) { $key = ($keyLine -split '=', 2)[1].Trim().Trim('"').Trim("'") }

Write-Host "Проверка api.elevenlabs.io через прокси..."
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
        Write-Host "ВНИМАНИЕ: ответ HTML (geo-block?). Нужен другой прокси/страна."
    } elseif ($r.Content -match '"voices"') {
        Write-Host "OK: JSON со списком голосов — прокси подходит."
    } else {
        Write-Host "Ответ не HTML, но без voices — смотрите тело вручную."
    }
} catch {
    Write-Host "Ошибка запроса через прокси: $($_.Exception.Message)"
    Write-Host "Для SOCKS5 PowerShell -Proxy может не подойти; после перезапуска бота проверьте /api/elevenlabs/ping"
}

Write-Host ""
Write-Host "Дальше: перезапустите бота (deploy_update.ps1) и откройте /api/elevenlabs/ping"
