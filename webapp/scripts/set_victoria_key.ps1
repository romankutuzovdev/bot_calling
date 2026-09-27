# Safe write of ElevenLabs key + Victoria voice without breaking script.json.
# Run from C:\bot_calling

$ErrorActionPreference = "Stop"
$Root = "C:\bot_calling"
Set-Location $Root

$key = "sk_804fad9ca9f4345f6caddb949b061ab0eafdca551824c085"
$proxy = "http://nr3E6AvS:mv5BSCY4@45.192.44.84:63352"
$voice = "FZGeNF7bE3syeQOynDKC"

$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines((Join-Path $Root ".env"), @(
  "ELEVENLABS_API_KEY=$key",
  "ELEVENLABS_PROXY=$proxy"
), $utf8)
Write-Host "OK .env"

# restore script.json from git if broken, then patch voice via Python (keeps UTF-8 JSON)
$scriptPath = Join-Path $Root "webapp\data\script.json"
$py = Join-Path $Root ".venv\Scripts\python.exe"
& $py -c @"
import json
from pathlib import Path
p = Path(r'$scriptPath')
try:
    data = json.loads(p.read_text(encoding='utf-8'))
except Exception as e:
    print('script.json broken, restoring defaults...', e)
    data = {}
data['tts_engine'] = 'elevenlabs'
data['elevenlabs_voice_id'] = '$voice'
data['elevenlabs_model'] = 'eleven_multilingual_v2'
data.setdefault('agent_name', 'Александра')
data.setdefault('company', 'МультиГлобал Групп')
data.setdefault('opening', 'Здравствуйте! Меня зовут Александра, компания МультиГлобал Групп. Удобно буквально минуту по грузоперевозкам?')
data.setdefault('ollama_model', 'qwen2.5:3b')
data.setdefault('ollama_url', 'http://127.0.0.1:11434')
data.setdefault('temperature', 0.35)
data.setdefault('tts_voice', 'ru-RU-SvetlanaNeural')
data.setdefault('tts_rate', '+8%')
data.setdefault('speaker_wav', 'voices/my_voice_22k.wav')
data.setdefault('system_prompt', data.get('system_prompt') or 'Ты — Александра, менеджер МультиГлобал.')
data['elevenlabs_api_key'] = ''
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('OK script.json voice=', data['elevenlabs_voice_id'], 'engine=', data['tts_engine'])
"@

Write-Host "Restart bot manually: .\webapp\scripts\deploy_update.ps1"
Write-Host "Then: Invoke-RestMethod http://127.0.0.1:8080/api/elevenlabs/ping"
