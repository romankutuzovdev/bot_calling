# ElevenLabs TTS

1. Аккаунт: https://elevenlabs.io  
2. **API Key**: Profile → API Keys  
3. **Клон Андрея**: Voices → Add / Instant Voice Clone → загрузите `voices/my_voice_22k.wav` (или andrey.ogg) → скопируйте **Voice ID**

## Важно: гео-блок

ElevenLabs **блокирует доступ с IP РФ/СНГ** (HTTP 302/403 → статья про restricted countries).  
Ключ и Voice ID при этом могут быть валидны — с сервера в запрещённой стране API не отвечает.

### Варианты

**A. HTTPS-прокси из разрешённой страны** (рекомендуется для Windows Server):

В `C:\bot_calling\.env`:
```
ELEVENLABS_API_KEY=xi-...
ELEVENLABS_PROXY=http://user:pass@PROXY_HOST:PORT
```

Проверка:
```powershell
$proxy = "http://user:pass@PROXY_HOST:PORT"
Invoke-WebRequest https://api.elevenlabs.io/v1/voices `
  -Proxy $proxy `
  -Headers @{ "xi-api-key" = "xi-..." } `
  -UseBasicParsing | Select StatusCode, RawContentLength
```
Ожидается **200** и JSON со списком голосов (не HTML).

**B. VPN на сервере** — исходящий IP должен быть не из blocked countries.

**C. Без ElevenLabs** — в UI выберите **Edge** или **XTTS (клон Андрея)**.

## На сервере

```powershell
cd C:\bot_calling
git pull
.\webapp\scripts\deploy_update.ps1
```

В UI: Голос → ElevenLabs → Voice ID → Сохранить → Прослушать.

Модель: `eleven_multilingual_v2`.
