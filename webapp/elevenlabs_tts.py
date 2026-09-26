"""ElevenLabs Text-to-Speech (HTTP API)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

DEFAULT_MODEL = "eleven_multilingual_v2"
API_BASE = "https://api.elevenlabs.io/v1"


def resolve_api_key(explicit: str | None = None) -> str | None:
    key = (explicit or "").strip() or os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    try:
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


def _preview(content: bytes, limit: int = 300) -> str:
    if not content:
        return "<empty body>"
    try:
        return content[:limit].decode("utf-8", errors="replace")
    except Exception:
        return repr(content[:limit])


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
    text = " ".join(text.split()).strip()
    if not text:
        raise ValueError("empty text")
    if not voice_id.strip():
        raise ValueError("elevenlabs_voice_id is empty")

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
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Нет доступа к api.elevenlabs.io с сервера: {exc}. "
            "Проверьте интернет/firewall/прокси Windows."
        ) from exc

    content = r.content or b""
    ct = (r.headers.get("content-type") or "").lower()

    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} ({ct}): {_preview(content)}")

    if not content:
        raise RuntimeError("ElevenLabs вернул пустое тело ответа")

    # валидный mp3: ID3 или frame sync
    if content[:3] == b"ID3" or (content[0] == 0xFF and (content[1] & 0xE0) == 0xE0):
        return content

    raise RuntimeError(
        f"Ожидали mp3, получили {len(content)} байт, Content-Type={ct}: {_preview(content)}"
    )


async def list_voices(api_key: str, timeout: float = 30.0) -> list[dict[str, str]]:
    headers = {"xi-api-key": api_key, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(f"{API_BASE}/voices", headers=headers)
    except httpx.RequestError as exc:
        raise RuntimeError(f"Нет доступа к api.elevenlabs.io: {exc}") from exc

    content = r.content or b""
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {_preview(content)}")
    if not content.strip():
        raise RuntimeError("Пустой ответ /v1/voices (firewall/прокси?)")

    try:
        data = r.json()
    except Exception as exc:
        raise RuntimeError(
            f"Ответ /v1/voices не JSON ({len(content)} байт): {_preview(content)}"
        ) from exc

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
