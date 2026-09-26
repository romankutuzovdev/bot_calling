"""ElevenLabs Text-to-Speech (HTTP API)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

DEFAULT_MODEL = "eleven_multilingual_v2"
API_BASE = "https://api.elevenlabs.io/v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

_GEO_HINT = (
    "ElevenLabs geo-blocks this server IP (302/403). "
    "Set ELEVENLABS_PROXY=http://user:pass@host:port in .env "
    "(EU/US proxy) or use VPN. Meanwhile use Edge/XTTS."
)


def _read_env_file() -> dict[str, str]:
    """Parse .env (UTF-8 with/without BOM)."""
    out: dict[str, str] = {}
    if not ENV_PATH.exists():
        return out
    try:
        text = ENV_PATH.read_text(encoding="utf-8-sig")
    except Exception:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip().lstrip("\ufeff")] = v.strip().strip('"').strip("'")
    return out


def resolve_api_key(explicit: str | None = None) -> str | None:
    key = (explicit or "").strip() or os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    key = (_read_env_file().get("ELEVENLABS_API_KEY") or "").strip()
    if key:
        return key
    try:
        secrets = Path(__file__).resolve().parent / "data" / "secrets.json"
        if secrets.exists():
            data = json.loads(secrets.read_text(encoding="utf-8"))
            k = (data.get("elevenlabs_api_key") or "").strip()
            if k:
                return k
    except Exception:
        pass
    return None


def resolve_proxy() -> str | None:
    for env_name in ("ELEVENLABS_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        val = (os.environ.get(env_name) or "").strip()
        if val:
            return val
    return (_read_env_file().get("ELEVENLABS_PROXY") or "").strip() or None


def proxy_host_hint() -> str | None:
    p = resolve_proxy()
    if not p:
        return None
    # hide credentials: scheme://user:pass@host:port -> host:port
    try:
        if "@" in p:
            return p.rsplit("@", 1)[-1]
        return p.split("://", 1)[-1]
    except Exception:
        return "(set)"


def _client(timeout: float) -> httpx.AsyncClient:
    proxy = resolve_proxy()
    kwargs: dict[str, Any] = {"timeout": timeout, "follow_redirects": False}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)


def _preview(content: bytes, limit: int = 300) -> str:
    if not content:
        return "<empty body>"
    try:
        return content[:limit].decode("utf-8", errors="replace")
    except Exception:
        return repr(content[:limit])


def _raise_if_geo_blocked(status: int, content: bytes) -> None:
    text = _preview(content, 800).lower()
    if status in (301, 302, 403) and (
        "restrict" in text
        or "specific-countries" in text
        or "302 moved" in text
        or "help.elevenlabs.io" in text
    ):
        hint = proxy_host_hint()
        extra = f" Current proxy: {hint}." if hint else " No ELEVENLABS_PROXY loaded."
        raise RuntimeError(_GEO_HINT + extra)


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
        async with _client(timeout) as client:
            r = await client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Cannot reach api.elevenlabs.io: {exc}. "
            "Check ELEVENLABS_PROXY or network."
        ) from exc

    content = r.content or b""
    ct = (r.headers.get("content-type") or "").lower()
    _raise_if_geo_blocked(r.status_code, content)

    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} ({ct}): {_preview(content)}")

    if not content:
        raise RuntimeError("ElevenLabs returned empty body")

    if content[:3] == b"ID3" or (content[0] == 0xFF and (content[1] & 0xE0) == 0xE0):
        return content

    raise RuntimeError(
        f"Expected mp3, got {len(content)} bytes, Content-Type={ct}: {_preview(content)}"
    )


async def list_voices(api_key: str, timeout: float = 30.0) -> list[dict[str, str]]:
    headers = {"xi-api-key": api_key, "Accept": "application/json"}
    try:
        async with _client(timeout) as client:
            r = await client.get(f"{API_BASE}/voices", headers=headers)
    except httpx.RequestError as exc:
        raise RuntimeError(f"Cannot reach api.elevenlabs.io: {exc}") from exc

    content = r.content or b""
    _raise_if_geo_blocked(r.status_code, content)

    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {_preview(content)}")
    if not content.strip():
        raise RuntimeError("Empty /v1/voices body")

    try:
        data = r.json()
    except Exception as exc:
        raise RuntimeError(
            f"/v1/voices not JSON ({len(content)} bytes): {_preview(content)}"
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
        return {
            "ok": True,
            "voices": len(voices),
            "proxy": bool(resolve_proxy()),
            "proxy_host": proxy_host_hint(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "proxy": bool(resolve_proxy()),
            "proxy_host": proxy_host_hint(),
        }
