"""
Веб-тестер голосового логистического бота.
Слушает 0.0.0.0:8080 — удобно для Windows Server.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
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


def _load_secrets() -> None:
    import os

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        raw = env_path.read_bytes()
        text = ""
        for enc in ("utf-8-sig", "utf-16", "utf-16-le", "cp1251"):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                continue
        for line in text.splitlines():
            line = line.strip().lstrip("\ufeff")
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    secrets = DATA / "secrets.json"
    if secrets.exists():
        try:
            s = json.loads(secrets.read_text(encoding="utf-8"))
            if s.get("elevenlabs_api_key"):
                os.environ.setdefault("ELEVENLABS_API_KEY", s["elevenlabs_api_key"])
        except Exception:
            pass


_load_secrets()

app = FastAPI(title="Bot Calling Web Tester", version="1.0.0")

# CORS: Vercel UI may call API directly; rewrite proxy is same-origin
from fastapi.middleware.cors import CORSMiddleware

_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def _norm(text: str) -> str:
    t = text.lower().replace("ё", "е")
    t = re.sub(r"[^a-zа-я0-9\s]", " ", t)
    return " ".join(t.split())


def quick_reply(user_text: str, user_turn: int) -> tuple[str, str | None] | None:
    """Быстрые ответы без Ollama для очевидных реплик (быстрее и правдивее)."""
    t = _norm(user_text)
    if not t:
        return "Вас плохо слышно. Повторите, пожалуйста?", None

    refuse = ("не звоните", "не надо", "не интересно", "удалите", "больше не")
    busy = ("занят", "неудобно", "некогда", "нет времени", "перезвон", "перезвоните", "позже", "сейчас не")
    yes = (
        "здравств",
        "здрасств",  # частая опечатка/ASR
        "добрый",
        "доброе",
        "добрый день",
        "алло",
        "слушаю",
        "говорите",
        "давайте",
        "удобно",
        "можно",
        "да ",
        " да",
        "ок",
        "окей",
        "хорошо",
        "конечно",
        "минуту",
    )

    if any(x in t for x in refuse):
        return "Понял вас. Хорошего дня!", "END_CALL"

    # первая реплика клиента после приветствия бота
    if user_turn <= 1:
        is_busy = any(x in t for x in busy)
        is_hello_or_yes = any(x in t for x in yes) or t in ("да", "угу", "ага", "йес")
        # «здравствуйте» ≠ занят
        if is_hello_or_yes and not (is_busy and not any(x in t for x in ("здравств", "здрасств", "добрый", "алло"))):
            return (
                "Отлично. Возим по Беларуси, России, СНГ, Европе, Турции и Китаю. "
                "Вы сами организуете перевозки или лучше к логисту?",
                None,
            )
        if is_busy:
            return "Понимаю. Когда удобнее перезвонить — сегодня позже или завтра?", None

    # повторное приветствие — не гоняем в LLM
    if user_turn <= 3 and any(x in t for x in ("здравств", "здрасств", "добрый", "алло")):
        return (
            "Да, на связи. Вы сами организуете перевозки или лучше связаться с логистом?",
            None,
        )

    return None


GUARD_RULE = (
    "КРИТИЧНО: если клиент сказал здравствуйте/добрый день/алло/слушаю/да/удобно — "
    "ему удобно говорить. НЕ спрашивай когда перезвонить. Сразу про потребность в перевозках."
)


class ScriptUpdate(BaseModel):
    agent_name: str = "Александра"
    company: str = "МультиГлобал Групп"
    opening: str
    system_prompt: str
    ollama_model: str = "qwen2.5:3b"
    ollama_url: str = "http://127.0.0.1:11434"
    temperature: float = 0.45
    tts_engine: str = "elevenlabs"  # elevenlabs | clone | edge
    tts_voice: str = "ru-RU-SvetlanaNeural"
    tts_rate: str = "+8%"
    speaker_wav: str = "voices/my_voice_22k.wav"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"


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


def ollama_cpu_threads() -> int:
    """Не меньше 50% логических ядер, по умолчанию — все ядра."""
    total = max(1, os.cpu_count() or 8)
    floor = max(1, (total + 1) // 2)  # >= 50%
    env = (os.environ.get("OLLAMA_NUM_THREAD") or os.environ.get("OLLAMA_NUM_THREADS") or "").strip()
    if env.isdigit() and int(env) > 0:
        return max(int(env), floor)
    # все ядра — максимальная утилизация на один запрос
    return total


def ollama_options(temperature: float) -> dict[str, Any]:
    """Максимальная загрузка CPU на один запрос к LLM (>= ~50% машины)."""
    n = ollama_cpu_threads()
    return {
        "temperature": temperature,
        "num_predict": int(os.environ.get("OLLAMA_NUM_PREDICT", "64")),
        "num_ctx": int(os.environ.get("OLLAMA_NUM_CTX", "1536")),
        "num_thread": n,
        "num_gpu": 0,
        "num_batch": int(os.environ.get("OLLAMA_NUM_BATCH", "1024")),
        "top_k": 40,
        "top_p": 0.9,
        "repeat_penalty": 1.1,
    }


async def ollama_warmup(base_url: str, model: str) -> None:
    """Держит модель в RAM и прогревает CPU-потоки."""
    payload = {
        "model": model,
        "prompt": "ok",
        "stream": False,
        "keep_alive": "60m",
        "options": {**ollama_options(0.0), "num_predict": 1},
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            await client.post(f"{base_url.rstrip('/')}/api/generate", json=payload)
    except Exception:
        pass


async def resolve_ollama_model(base_url: str, wanted: str) -> str:
    """Если модели нет (например 7b) — берём qwen2.5:3b или первую доступную."""
    wanted = (wanted or "qwen2.5:3b").strip() or "qwen2.5:3b"
    tags = await ollama_tags(base_url)
    if not tags:
        return wanted

    def present(name: str) -> bool:
        return any(name == t or t.startswith(name) or name in t for t in tags)

    if present(wanted):
        return wanted
    for fallback in ("qwen2.5:3b", "qwen2.5:1.5b", "llama3.2:3b", "llama3.2"):
        if present(fallback):
            return fallback
    # короткое имя без тега
    short = wanted.split(":")[0]
    for t in tags:
        if t.startswith(short):
            return t
    return tags[0]


async def ollama_chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
) -> str:
    model = await resolve_ollama_model(base_url, model)
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "60m",
        "options": ollama_options(temperature),
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(f"{base_url.rstrip('/')}/api/chat", json=payload)
            if r.status_code >= 400:
                text = r.text[:400]
                # ещё одна попытка на 3b
                if "not found" in text.lower() and model != "qwen2.5:3b":
                    payload["model"] = "qwen2.5:3b"
                    r2 = await client.post(f"{base_url.rstrip('/')}/api/chat", json=payload)
                    if r2.status_code >= 400:
                        raise HTTPException(502, f"Ollama error: {r2.text[:400]}")
                    return (r2.json().get("message") or {}).get("content", "").strip()
                raise HTTPException(502, f"Ollama error: {text}")
            return (r.json().get("message") or {}).get("content", "").strip()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            503,
            f"Ollama недоступна ({base_url}). Запустите Ollama и: ollama pull qwen2.5:3b. Детали: {exc}",
        ) from exc


@app.on_event("startup")
async def _startup_warmup_ollama() -> None:
    try:
        script = load_script()
        base = script.get("ollama_url", "http://127.0.0.1:11434")
        model = script.get("ollama_model", "qwen2.5:3b")
        asyncio.create_task(ollama_warmup(base, model))
    except Exception:
        pass


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
        "engine": script.get("tts_engine", "elevenlabs"),
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
    from webapp.elevenlabs_tts import resolve_api_key

    el_key = resolve_api_key(script.get("elevenlabs_api_key"))
    eleven = {
        "configured": bool(el_key),
        "voice_id": (script.get("elevenlabs_voice_id") or "").strip()[:12] + "…"
        if (script.get("elevenlabs_voice_id") or "").strip()
        else "",
        "voice_id_set": bool((script.get("elevenlabs_voice_id") or "").strip()),
    }
    return {
        "ok": ok,
        "ollama_url": base,
        "model": model,
        "models": models,
        "ollama_cpu_threads": ollama_cpu_threads(),
        "port": 8080,
        "tts_engine": script.get("tts_engine", "elevenlabs"),
        "clone": clone_info,
        "elevenlabs": eleven,
    }


@app.get("/api/script")
async def get_script() -> dict[str, Any]:
    data = load_script()
    # не отдаём ключ в открытом виде
    key = (data.get("elevenlabs_api_key") or "").strip()
    data = dict(data)
    data["elevenlabs_api_key_set"] = bool(key) or bool(
        __import__("os").environ.get("ELEVENLABS_API_KEY")
    )
    if key:
        data["elevenlabs_api_key"] = ""
    return data


@app.put("/api/script")
async def put_script(body: ScriptUpdate) -> dict[str, Any]:
    current = load_script()
    data = body.model_dump()
    # пустой ключ в форме = не затирать сохранённый / env
    if not (data.get("elevenlabs_api_key") or "").strip():
        data.pop("elevenlabs_api_key", None)
    current.update(data)
    save_script(current)
    safe = dict(current)
    if safe.get("elevenlabs_api_key"):
        safe["elevenlabs_api_key"] = ""
        safe["elevenlabs_api_key_set"] = True
    return {"saved": True, "script": safe}


@app.get("/api/voices")
async def list_voices() -> dict[str, Any]:
    return {
        "voices": [
            {"id": "ru-RU-SvetlanaNeural", "label": "Светлана (жен., живой)"},
            {"id": "ru-RU-DariyaNeural", "label": "Дария (жен., живой)"},
            {"id": "ru-RU-DmitryNeural", "label": "Дмитрий (муж., живой)"},
        ]
    }


async def synthesize_edge_mp3(text: str, voice: str, rate: str) -> bytes:
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
        raise HTTPException(502, "Edge TTS не вернул аудио")
    return audio


@app.post("/api/tts")
async def tts(body: TtsIn) -> Response:
    """
    TTS engines:
    - elevenlabs = облачный (нужен платный план для library voices)
    - clone / xtts = локальный XTTS
    - edge = Microsoft Neural (бесплатно, хороший русский женский)
    """
    script = load_script()
    engine = (body.engine or script.get("tts_engine") or "edge").lower()
    text = " ".join(body.text.split())
    if not text:
        raise HTTPException(400, "Пустой текст")

    edge_voice = body.voice if (body.voice or "").startswith("ru-RU-") else None
    edge_voice = edge_voice or script.get("tts_voice") or "ru-RU-SvetlanaNeural"
    edge_rate = body.rate or script.get("tts_rate") or "+8%"

    if engine in ("elevenlabs", "11labs", "eleven"):
        try:
            from webapp.elevenlabs_tts import resolve_api_key, synthesize_mp3
        except ImportError:
            from elevenlabs_tts import resolve_api_key, synthesize_mp3  # type: ignore

        api_key = resolve_api_key(script.get("elevenlabs_api_key"))
        raw_voice = (body.voice or "").strip()
        voice_id = raw_voice or (script.get("elevenlabs_voice_id") or "").strip()
        if not api_key:
            raise HTTPException(
                400,
                "Нет API key. Создайте C:\\bot_calling\\.env с ELEVENLABS_API_KEY=... "
                "или вставьте ключ в UI. На Free плане library-голоса через API недоступны — выберите Edge.",
            )
        if not voice_id:
            raise HTTPException(
                400,
                "Нет Voice ID. На Free плане лучше голос Edge: ru-RU-SvetlanaNeural.",
            )
        try:
            audio = await synthesize_mp3(
                text,
                api_key=api_key,
                voice_id=voice_id,
                model_id=script.get("elevenlabs_model") or "eleven_multilingual_v2",
            )
        except Exception as exc:
            err = str(exc)
            # Free plan: library voices blocked → auto Edge female RU
            if "402" in err or "paid_plan" in err.lower() or "payment_required" in err.lower():
                audio = await synthesize_edge_mp3(text, "ru-RU-SvetlanaNeural", edge_rate)
                return Response(
                    content=audio,
                    media_type="audio/mpeg",
                    headers={
                        "Cache-Control": "no-store",
                        "X-TTS-Fallback": "edge-svetlana",
                        "X-TTS-Fallback-Reason": "elevenlabs-paid-plan-required",
                    },
                )
            raise HTTPException(502, f"ElevenLabs: {exc}") from exc
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store", "Accept-Ranges": "bytes"},
        )

    if engine in ("clone", "xtts"):
        try:
            from src.tts import synthesize_clone_bytes
        except Exception as exc:
            raise HTTPException(
                500,
                f"XTTS не установлен. На сервере: pip install coqui-tts (Python 3.12). ({exc})",
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

    # edge (default free path)
    audio = await synthesize_edge_mp3(text, edge_voice, edge_rate)
    return Response(content=audio, media_type="audio/mpeg")


@app.get("/api/elevenlabs/ping")
async def elevenlabs_ping() -> dict[str, Any]:
    """Диагностика ключа и Voice ID без генерации длинного аудио."""
    try:
        from webapp.elevenlabs_tts import check_key, resolve_api_key, synthesize_mp3
    except ImportError:
        from elevenlabs_tts import check_key, resolve_api_key, synthesize_mp3  # type: ignore

    script = load_script()
    api_key = resolve_api_key(script.get("elevenlabs_api_key"))
    voice_id = (script.get("elevenlabs_voice_id") or "").strip()
    out: dict[str, Any] = {
        "has_key": bool(api_key),
        "voice_id": voice_id,
        "model": script.get("elevenlabs_model") or "eleven_multilingual_v2",
        "engine": script.get("tts_engine"),
    }
    if not api_key:
        out["ok"] = False
        out["error"] = "no api key (.env / secrets.json / UI)"
        return out
    chk = await check_key(api_key)
    out["voices_api"] = chk
    if not chk.get("ok"):
        out["ok"] = False
        out["error"] = chk.get("error")
        return out
    if not voice_id:
        out["ok"] = False
        out["error"] = "no voice_id"
        return out
    try:
        audio = await synthesize_mp3(
            "Привет, это тест.",
            api_key=api_key,
            voice_id=voice_id,
            model_id=out["model"],
        )
        out["ok"] = True
        out["audio_bytes"] = len(audio)
    except Exception as exc:
        out["ok"] = False
        out["error"] = str(exc)
    return out


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

    user_turns = sum(1 for m in messages if m.get("role") == "user")
    fast = quick_reply(user_text, user_turns)
    if fast:
        spoken, flag = fast
        messages.append({"role": "assistant", "content": spoken})
        SESSIONS[sid] = messages
        return {
            "session_id": sid,
            "reply": spoken,
            "flag": flag,
            "agent_name": script.get("agent_name", "Бот"),
            "voice_style_applied": False,
            "fast_path": True,
        }

    # для запроса — с подсказкой стиля, в сессии храним чистый текст
    send_messages = list(messages)
    # усиливаем правило на каждом ходе
    send_messages[0] = {
        "role": "system",
        "content": f"{script['system_prompt']}\n\n{GUARD_RULE}",
    }
    hint = style_from_profile(body.voice_profile)
    if hint:
        send_messages[-1] = {
            "role": "user",
            "content": f"{user_text}\n\n(Служебная подсказка стиля — не упоминай клиенту):\n{hint}",
        }

    # обрезаем историю
    send_messages = [send_messages[0]] + send_messages[1:][-8:]

    reply_raw = await ollama_chat(
        script.get("ollama_url", "http://127.0.0.1:11434"),
        script.get("ollama_model", "qwen2.5:3b"),
        send_messages,
        float(script.get("temperature", 0.35)),
    )
    spoken, flag = clean_flags(reply_raw)
    if not spoken:
        spoken = "Понял вас. Подскажите, пожалуйста, ещё раз?"

    # страховка: модель снова ушла в «перезвонить» после приветствия
    low = _norm(spoken)
    if user_turns <= 1 and "перезвон" in low and any(
        x in _norm(user_text) for x in ("здравств", "здрасств", "добрый", "алло", "слушаю")
    ):
        spoken = (
            "Отлично. Возим по Беларуси, России, СНГ, Европе, Турции и Китаю. "
            "Вы сами организуете перевозки или лучше к логисту?"
        )
        flag = None

    messages.append({"role": "assistant", "content": spoken})
    SESSIONS[sid] = messages

    return {
        "session_id": sid,
        "reply": spoken,
        "flag": flag,
        "agent_name": script.get("agent_name", "Бот"),
        "voice_style_applied": bool(hint),
        "fast_path": False,
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
