# List own ElevenLabs voices (generated/cloned) and optionally set one.
# Usage:
#   .\webapp\scripts\list_el_voices.ps1
#   .\webapp\scripts\list_el_voices.ps1 -SetName "My Voice 2"
#   .\webapp\scripts\list_el_voices.ps1 -VoiceId "xxxx"

param(
  [string]$SetName = "",
  [string]$VoiceId = "",
  [string]$Root = "C:\bot_calling"
)

$ErrorActionPreference = "Stop"
Set-Location $Root
$py = Join-Path $Root ".venv\Scripts\python.exe"

& $py -c @"
import asyncio, json, sys
from pathlib import Path
from webapp.elevenlabs_tts import resolve_api_key, list_voices

async def main():
    key = resolve_api_key()
    if not key:
        print('NO_KEY')
        sys.exit(1)
    voices = await list_voices(key)
    own = [v for v in voices if (v.get('category') or '') in ('generated', 'cloned')]
    print('=== OWN VOICES (Free API OK) ===')
    for i, v in enumerate(own, 1):
        print(f\"{i}. [{v['category']}] {v['voice_id']}  {v['name']}\")
    print('=== ALL non-premade ===')
    for v in voices:
        if (v.get('category') or '') != 'premade':
            print(f\"[{v['category']}] {v['voice_id']}  {v['name']}\")

    set_name = r'''$SetName'''.strip()
    set_id = r'''$VoiceId'''.strip()
    chosen = None
    if set_id:
        chosen = next((v for v in voices if v.get('voice_id') == set_id), None)
    elif set_name:
        low = set_name.lower()
        for v in own:
            if low in (v.get('name') or '').lower():
                chosen = v
                break
        if not chosen:
            for v in voices:
                if low in (v.get('name') or '').lower():
                    chosen = v
                    break
    elif len(own) >= 2:
        # second own voice by default if My Boice is first
        chosen = own[1]
        print('AUTO pick #2:', chosen['voice_id'], chosen['name'])
    elif len(own) == 1:
        chosen = own[0]
        print('AUTO pick only own:', chosen['voice_id'], chosen['name'])

    if not chosen:
        print('NOTHING_TO_SET')
        return

    p = Path('webapp/data/script.json')
    d = json.loads(p.read_text(encoding='utf-8'))
    d['tts_engine'] = 'elevenlabs'
    d['elevenlabs_voice_id'] = chosen['voice_id']
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SET', chosen['voice_id'], chosen['name'])

asyncio.run(main())
"@
