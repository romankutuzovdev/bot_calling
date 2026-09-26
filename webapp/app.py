"""
Веб-тестер голосового логистического бота.
Слушает 0.0.0.0:8080 — удобно для Windows Server.
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

WEB_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_ROOT.parent
DATA = WEB_ROOT / "data"
SCRIPT_PATH = DATA / "script.json"
STATIC = WEB_ROOT / "static"

DATA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Bot Calling Web Tester", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

# session_id -> list of {role, content}
SESSIONS: dict[str, list[dict[str, str]]] = {}


def load_script() -> dict[str, Any]:
    if not SCRIPT_PATH.exists():
        raise HTTPException(500, "script.json не найден")
    return json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))


def save_script(data: dict[str, Any]) -> None:
    SCRIPT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clean_flags(text: str) -> tuple[str, str | None]:
    flag = None
    if re.search(r"\bCLOSE_DEAL\b", text):
        flag = "CLOSE_DEAL"
    elif re.search(r"\bEND_CALL\b", text):
        flag = "END_CALL"
    spoken = text.replace("CLOSE_DEAL", "").replace("END_CALL", "")
    for ch in ("*", "#", "`", "•"):
        spoken = spoken.replace(ch, "")
    return " ".join(spoken.split()).strip(), flag


class ScriptUpdate(BaseModel):
    agent_name: str = "Александра"
    company: str = "МультиГлобал Групп"
    opening: str
    system_prompt: str
    ollama_model: str = "qwen2.5:3b"
    ollama_url: str = "http://127.0.0.1:11434"
    temperature: float = 0.45
    tts_engine: str = "clone"  # clone = XTTS ваш голос | edge = Microsoft
    tts_voice: str = "ru-RU-SvetlanaNeural"
    tts_rate: str = "+8%"
    speaker_wav: str = "voices/my_voice_22k.wav"


class TtsIn(BaseModel):
    text: str = Field(..., min_length=1)
    voice: str | None = None
    rate: str | None = None
    engine: str | None = None


class VoiceProfileIn(BaseModel):
    gender: str | None = None
    emotion: str | None = None
    tempo: str | None = None


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1)
    voice_profile: VoiceProfileIn | None = None
    reset: bool = False


def style_from_profile(vp: VoiceProfileIn | None) -> str | None:
    if not vp:
        return None
    parts = [
        "Подстрой стиль ответа под голос собеседника (эвристика, не утверждай вслух):"
    ]
    if vp.gender == "female":
        parts.append("- Тон чуть мягче, без грубого давления.")
    elif vp.gender == "male":
        parts.append("- Тон деловой и прямой.")
    if vp.emotion == "tense":
        parts.append("- Звучит напряжённо: снизь давление, один мягкий вопрос.")
    elif vp.emotion == "engaged":
        parts.append("- Вовлечён: быстрее к сути и следующему шагу.")
    elif vp.emotion == "calm":
        parts.append("- Спокоен: спокойный темп, без агрессивного дожима.")
    if vp.tempo == "fast":
        parts.append("- Говорит быстро: 1 фраза + 1 вопрос.")
    elif vp.tempo == "slow":
        parts.append("- Говорит медленно: простые формулировки.")
    parts.append("- Не говори клиенту, что анализируешь голос.")
    return "\n".join(parts)


async def ollama_tags(base_url: str) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            return [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return []


async def ollama_chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": 90},
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{base_url.rstrip('/')}/api/chat", json=payload)
            if r.status_code >= 400:
                raise HTTPException(502, f"Ollama error: {r.text[:400]}")
            return (r.json().get("message") or {}).get("content", "").strip()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            503,
            f"Ollama недоступна ({base_url}). Запустите Ollama и: ollama pull {model}. Детали: {exc}",
        ) from exc


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    script = load_script()
    base = script.get("ollama_url", "http://127.0.0.1:11434")
    model = script.get("ollama_model", "qwen2.5:3b")
    models = await ollama_tags(base)
    ok = any(model in m or m.startswith(model.split(":")[0]) for m in models)

    # Проверка сэмпла без тяжёлого import src.tts (rich/torch могут отсутствовать)
    rel = script.get("speaker_wav") or "voices/my_voice_22k.wav"
    candidates = [
        PROJECT_ROOT / rel,
        PROJECT_ROOT / "voices" / "my_voice_22k.wav",
        Path(r"C:\bot_calling") / rel,
        Path(r"C:\bot_calling\voices\my_voice_22k.wav"),
    ]
    speaker_path = None
    for c in candidates:
        try:
            if c.is_file() and c.stat().st_size > 1000:
                speaker_path = str(c.resolve())
                break
        except OSError:
            continue

    clone_info: dict[str, Any] = {
        "engine": script.get("tts_engine", "clone"),
        "device": "cpu",
        "speaker_ok": speaker_path is not None,
        "speaker_path": speaker_path or f"not found (looked under {PROJECT_ROOT / 'voices'})",
        "root": str(PROJECT_ROOT),
        "model_loaded": False,
        "note": (
            "Сэмпл найден"
            if speaker_path
            else "Положите WAV в voices\\my_voice_22k.wav и перезапустите бота"
        ),
    }
    return {
        "ok": ok,
        "ollama_url": base,
        "model": model,
        "models": models,
        "port": 8080,
        "tts_engine": script.get("tts_engine", "clone"),
        "clone": clone_info,
    }


@app.get("/api/script")
async def get_script() -> dict[str, Any]:
    return load_script()


@app.put("/api/script")
async def put_script(body: ScriptUpdate) -> dict[str, Any]:
    current = load_script()
    data = body.model_dump()
    # не затираем неизвестные поля
    current.update(data)
    save_script(current)
    return {"saved": True, "script": current}


@app.get("/api/voices")
async def list_voices() -> dict[str, Any]:
    return {
        "voices": [
            {"id": "ru-RU-SvetlanaNeural", "label": "Светлана (жен., живой)"},
            {"id": "ru-RU-DariyaNeural", "label": "Дария (жен., живой)"},
            {"id": "ru-RU-DmitryNeural", "label": "Дмитрий (муж., живой)"},
        ]
    }


@app.post("/api/tts")
async def tts(body: TtsIn) -> Response:
    """
    TTS:
    - clone = XTTS, генерация с вашего сэмпла (CPU, медленно, максимально «живой»)
    - edge  = Microsoft Neural (быстро)
    """
    script = load_script()
    engine = (body.engine or script.get("tts_engine") or "clone").lower()
    text = " ".join(body.text.split())
    if not text:
        raise HTTPException(400, "Пустой текст")

    if engine in ("clone", "xtts"):
        try:
            from src.tts import synthesize_clone_bytes
        except Exception as exc:
            raise HTTPException(
                500,
                f"XTTS не установлен. На сервере: pip install -r requirements.txt. ({exc})",
            ) from exc
        try:
            wav = await asyncio.to_thread(
                synthesize_clone_bytes,
                text,
                script.get("speaker_wav"),
            )
        except FileNotFoundError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"XTTS ошибка: {exc}") from exc
        if not wav:
            raise HTTPException(502, "XTTS не вернул аудио")
        return Response(content=wav, media_type="audio/wav")

    # fallback / edge
    voice = body.voice or script.get("tts_voice") or "ru-RU-SvetlanaNeural"
    rate = body.rate or script.get("tts_rate") or "+8%"
    try:
        import edge_tts
    except ImportError as exc:
        raise HTTPException(500, "Установите edge-tts: pip install edge-tts") from exc

    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    audio = buf.getvalue()
    if not audio:
        raise HTTPException(502, "TTS не вернул аудио")
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/api/session/reset")
async def reset_session(session_id: str | None = None) -> dict[str, Any]:
    sid = session_id or str(uuid.uuid4())
    script = load_script()
    opening = script["opening"].strip()
    SESSIONS[sid] = [
        {"role": "system", "content": script["system_prompt"]},
        {"role": "assistant", "content": opening},
    ]
    return {
        "session_id": sid,
        "opening": opening,
        "agent_name": script.get("agent_name", "Бот"),
        "company": script.get("company", ""),
    }


@app.post("/api/chat")
async def chat(body: ChatIn) -> dict[str, Any]:
    script = load_script()
    sid = body.session_id or str(uuid.uuid4())

    if body.reset or sid not in SESSIONS:
        opening = script["opening"].strip()
        SESSIONS[sid] = [
            {"role": "system", "content": script["system_prompt"]},
            {"role": "assistant", "content": opening},
        ]

    messages = SESSIONS[sid]
    user_text = body.message.strip()
    messages.append({"role": "user", "content": user_text})

    # для запроса — с подсказкой стиля, в сессии храним чистый текст
    send_messages = list(messages)
    hint = style_from_profile(body.voice_profile)
    if hint:
        send_messages[-1] = {
            "role": "user",
            "content": f"{user_text}\n\n(Служебная подсказка стиля — не упоминай клиенту):\n{hint}",
        }

    # обрезаем историю
    send_messages = [send_messages[0]] + send_messages[1:][-10:]

    reply_raw = await ollama_chat(
        script.get("ollama_url", "http://127.0.0.1:11434"),
        script.get("ollama_model", "qwen2.5:3b"),
        send_messages,
        float(script.get("temperature", 0.45)),
    )
    spoken, flag = clean_flags(reply_raw)
    if not spoken:
        spoken = "Поняла вас. Подскажите, пожалуйста, ещё раз?"

    messages.append({"role": "assistant", "content": spoken})
    SESSIONS[sid] = messages

    return {
        "session_id": sid,
        "reply": spoken,
        "flag": flag,
        "agent_name": script.get("agent_name", "Бот"),
        "voice_style_applied": bool(hint),
    }


def main() -> None:
    import uvicorn

    uvicorn.run(
        "webapp.app:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )


if __name__ == "__main__":
    main()
