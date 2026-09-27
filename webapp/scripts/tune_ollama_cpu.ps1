# Max CPU for fast Ollama replies on Windows Server.
# Run PowerShell as Administrator once, then restart the bot.
# ASCII-only for Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
$cores = [Environment]::ProcessorCount
Write-Host "Logical CPU cores: $cores -> Ollama will use ALL of them"

# Machine-wide (survives reboot; Ollama app reads these)
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "1", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "1", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_THREAD", "$cores", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "60m", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "0", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_BATCH", "1024", "Machine")
[Environment]::SetEnvironmentVariable("OMP_NUM_THREADS", "$cores", "Machine")

$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_NUM_THREAD = "$cores"
$env:OLLAMA_NUM_BATCH = "1024"
$env:OLLAMA_KEEP_ALIVE = "60m"
$env:OMP_NUM_THREADS = "$cores"

function Set-OllamaPriority {
  Get-Process -Name "ollama","ollama app" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
      $_.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::High
      Write-Host "Priority High: $($_.ProcessName) PID $($_.Id)"
    } catch {
      Write-Host "Priority skip PID $($_.Id): $($_.Exception.Message)"
    }
  }
}

$svc = Get-Service -Name "Ollama" -ErrorAction SilentlyContinue
if ($svc) {
  Restart-Service Ollama -Force
  Start-Sleep 4
} else {
  Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep 2
  $ollamaExe = @(
    "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "C:\Program Files\Ollama\ollama.exe"
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($ollamaExe) { Start-Process $ollamaExe; Start-Sleep 4 }
}

Set-OllamaPriority

# 3b = fastest for phone replies; keep in RAM
Write-Host "Ensure qwen2.5:3b is present..."
try { ollama pull qwen2.5:3b } catch { Write-Host "pull skipped: $_" }

Write-Host "Warmup 3b on $cores threads (watch Task Manager CPU)..."
$body = @{
  model = "qwen2.5:3b"
  prompt = "Скажи одно слово: ок"
  stream = $false
  keep_alive = "60m"
  options = @{
    num_thread = $cores
    num_gpu = 0
    num_batch = 1024
    num_predict = 8
    num_ctx = 1024
  }
} | ConvertTo-Json -Depth 5

try {
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method Post -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 180 | Out-Null
  $sw.Stop()
  Write-Host ("Warmup OK in {0:N1}s — ollama should spike CPU" -f ($sw.Elapsed.TotalSeconds))
} catch {
  Write-Host "Warmup failed: $($_.Exception.Message)"
}

Set-OllamaPriority
Write-Host ""
Write-Host "DONE. Keep model qwen2.5:3b in the UI (faster than 7b)."
Write-Host "Then restart bot: .\webapp\scripts\deploy_update.ps1"
Write-Host "Note: tiny models may not fill 100% of a 24-core box; all threads are still used for one request."
