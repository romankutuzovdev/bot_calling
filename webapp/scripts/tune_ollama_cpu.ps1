# Force Ollama to use >= 50% CPU (all logical cores, high priority).
# Run as Administrator.

$ErrorActionPreference = "Stop"
$cores = [Environment]::ProcessorCount
$minHalf = [Math]::Max(1, [Math]::Ceiling($cores / 2.0))
Write-Host "CPU logical cores: $cores (min floor 50% = $minHalf) -> using ALL $cores threads"

[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "1", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "1", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_THREAD", "$cores", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "60m", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "0", "Machine")

$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_NUM_THREAD = "$cores"
$env:OLLAMA_NUM_BATCH = "1024"
$env:OLLAMA_KEEP_ALIVE = "60m"

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

# Heavier model uses more CPU (3b often cannot fill a 16-24 core box to 50%)
Write-Host "Pulling qwen2.5:7b for higher CPU load (optional but recommended)..."
try { ollama pull qwen2.5:7b } catch { Write-Host "pull skipped: $_" }

Write-Host "Warmup 7b on $cores threads..."
$body = @{
  model = "qwen2.5:7b"
  prompt = "Скажи ок"
  stream = $false
  keep_alive = "60m"
  options = @{
    num_thread = $cores
    num_gpu = 0
    num_batch = 1024
    num_predict = 16
    num_ctx = 1024
  }
} | ConvertTo-Json -Depth 5

try {
  Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method Post -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 300 | Out-Null
  Write-Host "Warmup OK — watch Task Manager: ollama should spike CPU"
} catch {
  Write-Host "Warmup failed: $($_.Exception.Message)"
}

Set-OllamaPriority
Write-Host "DONE. Set ollama_model to qwen2.5:7b in UI or script.json, then restart bot."
Write-Host "If CPU still <50% on 3b — that model is too small for $cores cores; use 7b."
