# ElevenLabs TTS

1. Аккаунт: https://elevenlabs.io  
2. **API Key**: Profile → API Keys  
3. **Клон Андрея**: Voices → Add / Instant Voice Clone → загрузите `voices/my_voice_22k.wav` (или andrey.ogg) → скопируйте **Voice ID**

## На сервере

```powershell
cd C:\bot_calling
git pull
# перезапуск бота
.\webapp\scripts\deploy_update.ps1
```

В UI:
1. Голос → **Андрей — ElevenLabs**
2. Вставьте API key и Voice ID
3. **Сохранить скрипт** → **Прослушать**

Либо без UI (переменная окружения):
```powershell
$env:ELEVENLABS_API_KEY = "xi-..."
```
Voice ID всё равно задайте в UI / `webapp/data/script.json` → `elevenlabs_voice_id`.

Модель по умолчанию: `eleven_multilingual_v2` (русский).
