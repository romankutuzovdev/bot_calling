"""ElevenLabs Text-to-Speech (HTTP API)."""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_MODEL = "eleven_multilingual_v2"
API_BASE = "https://api.elevenlabs.io/v1"


def resolve_api_key(explicit: str | None = None) -> str | None:
    key = (explicit or "").strip() or os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    # optional local secrets file (gitignored)
    try:
        from pathlib import Path
        import json

        for p in (
            Path(__file__).resolve().parent / "data" / "secrets.json",
            Path(__file__).resolve().parents[1] / ".env",
        ):
            if p.name == ".env" and p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("ELEVENLABS_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            elif p.suffix == ".json" and p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                k = (data.get("elevenlabs_api_key") or "").strip()
                if k:
                    return k
    except Exception:
        pass
    return None


async def synthesize_mp3(
    text: str,
    *,
    api_key: str,
    voice_id: str,
    model_id: str = DEFAULT_MODEL,
    stability: float = 0.55,
    similarity_boost: float = 0.80,
    style: float = 0.10,
    timeout: float = 60.0,
) -> bytes:
    """Generate MP3 via ElevenLabs TTS.
    stability↑ = меньше запинок/скачков, чуть менее эмоционально.
    """
    text = " ".join(text.split()).strip()
    if not text:
        raise ValueError("empty text")
    if not voice_id.strip():
        raise ValueError("elevenlabs_voice_id is empty — paste Voice ID from ElevenLabs")

    # короткие фразы без «рваных» многоточий — меньше спотыканий
    text = text.replace("…", ".").replace("...", ".")

    url = f"{API_BASE}/text-to-speech/{voice_id.strip()}"
    payload: dict[str, Any] = {
        "text": text,
        "model_id": model_id or DEFAULT_MODEL,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": True,
        },
    }
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:500]}")
        audio = r.content
        if not audio:
            raise RuntimeError("ElevenLabs returned empty audio")
        return audio


async def list_voices(api_key: str, timeout: float = 30.0) -> list[dict[str, str]]:
    headers = {"xi-api-key": api_key}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(f"{API_BASE}/voices", headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()
    out: list[dict[str, str]] = []
    for v in data.get("voices") or []:
        out.append(
            {
                "voice_id": v.get("voice_id") or "",
                "name": v.get("name") or "",
                "category": v.get("category") or "",
            }
        )
    return out


async def check_key(api_key: str) -> dict[str, Any]:
    try:
        voices = await list_voices(api_key)
        return {"ok": True, "voices": len(voices)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
