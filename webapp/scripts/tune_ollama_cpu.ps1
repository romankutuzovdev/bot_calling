# Maximize Ollama CPU usage on Windows Server. Run as Administrator once.
# Sets machine env so the Ollama service uses all cores for one request.

$ErrorActionPreference = "Stop"
$cores = [Environment]::ProcessorCount
Write-Host "CPU logical cores: $cores"

# One request gets all threads (do not parallelize many chats on CPU)
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "1", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "1", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_THREAD", "$cores", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "60m", "Machine")

# Also for current session / bot process
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_NUM_THREAD = "$cores"
$env:OLLAMA_NUM_BATCH = "512"

Write-Host "Machine env set:"
Write-Host "  OLLAMA_NUM_PARALLEL=1"
Write-Host "  OLLAMA_NUM_THREAD=$cores"
Write-Host "  OLLAMA_KEEP_ALIVE=60m"

$svc = Get-Service -Name "Ollama" -ErrorAction SilentlyContinue
if ($svc) {
  Write-Host "Restarting Ollama service..."
  Restart-Service Ollama -Force
  Start-Sleep 3
  Write-Host "Ollama status: $((Get-Service Ollama).Status)"
} else {
  Write-Host "Service 'Ollama' not found. Quit Ollama tray app and start it again so it picks up env."
  Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep 1
  $ollamaExe = @(
    "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "C:\Program Files\Ollama\ollama.exe"
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($ollamaExe) {
    Start-Process $ollamaExe
    Write-Host "Started $ollamaExe"
  }
}

Write-Host "Warmup model..."
try {
  ollama run qwen2.5:3b "ok" 2>$null | Out-Null
} catch {}
Write-Host "DONE. Restart bot (deploy_update.ps1). Check Task Manager CPU during chat."
