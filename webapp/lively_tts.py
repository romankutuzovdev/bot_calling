"""Живая речь для Edge Neural TTS: паузы, интонация, разговорный темп."""
from __future__ import annotations

import io
import re
from typing import Iterable

# Короткая тишина (~280 мс, MP3 24 kHz mono) — склейка ADTS-кадров.
# Сгенерировано как валидный MPEG ADTS silence; браузеры и плееры принимают.
_SILENCE_FRAME = bytes.fromhex(
    "fff348c400000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000"
)
# ~35–40 мс на кадр → 7 кадров ≈ 250–280 мс
SILENCE_280MS = _SILENCE_FRAME * 7
SILENCE_150MS = _SILENCE_FRAME * 4


def humanize_spoken(text: str) -> str:
    """Готовит текст под устную речь: дыхание, паузы, без канцелярита."""
    t = " ".join(str(text).split()).strip()
    if not t:
        return ""

    # убрать служебные флаги, если проскочили
    t = re.sub(r"\b(CLOSE_DEAL|END_CALL)\b", "", t)
    t = re.sub(r"[*#`•]+", "", t)
    t = " ".join(t.split())

    # многоточие / тире → естественная пауза для нейросети
    t = t.replace("...", "…").replace("—", " — ").replace("–", " — ")

    # после приветствий чуть мягче
    t = re.sub(r"^(Здравствуйте)([!.]?\s*)", r"\1… ", t, flags=re.I)
    t = re.sub(r"^(Добрый день)([!.]?\s*)", r"\1… ", t, flags=re.I)

    # длинные куски без знаков — вставить дыхание перед союзами
    def breath(m: re.Match[str]) -> str:
        return f"{m.group(1)}, {m.group(2)}"

    t = re.sub(
        r"([а-яА-ЯёЁ]{4,})\s+(и|а|но|или|чтобы)\s+",
        breath,
        t,
        count=2,
    )

    # вопросительные хвосты — сохранить ?
    if not t.endswith((".", "!", "?", "…")):
        t += "."

    return " ".join(t.split())


def split_phrases(text: str) -> list[str]:
    """Режет на фразы по точке/вопросу/восклицанию/многоточию."""
    t = humanize_spoken(text)
    if not t:
        return []
    parts = re.split(r"(?<=[.!?…])\s+", t)
    return [p.strip() for p in parts if p.strip()]


def phrase_prosody(phrase: str, liveliness: str = "lively") -> tuple[str, str]:
    """
    rate, pitch для одной фразы.
    lively = разговорный менеджер; energetic = чуть быстрее; calm = мягче.
    """
    base = {
        "calm": ("+2%", "+2Hz"),
        "lively": ("+7%", "+5Hz"),
        "energetic": ("+12%", "+8Hz"),
    }.get(liveliness, ("+7%", "+5Hz"))

    rate, pitch = base
    # вопрос — выше тон, чуть быстрее
    if phrase.rstrip().endswith("?"):
        rate = {
            "calm": "+4%",
            "lively": "+9%",
            "energetic": "+14%",
        }.get(liveliness, "+9%")
        pitch = {
            "calm": "+6Hz",
            "lively": "+12Hz",
            "energetic": "+15Hz",
        }.get(liveliness, "+12Hz")
    # короткое согласие / реакция
    elif len(phrase) < 28 and re.search(
        r"^(хорошо|поняла|отлично|договорились|спасибо|хорошо)\b",
        phrase,
        re.I,
    ):
        pitch = "+8Hz" if liveliness != "calm" else "+4Hz"

    return rate, pitch


async def synthesize_lively_mp3(
    text: str,
    voice: str = "ru-RU-SvetlanaNeural",
    liveliness: str = "lively",
    rate_override: str | None = None,
    pitch_override: str | None = None,
) -> bytes:
    """Синтез с паузами между фразами и разной интонацией."""
    import edge_tts

    phrases = split_phrases(text)
    if not phrases:
        return b""

    out = io.BytesIO()
    for i, phrase in enumerate(phrases):
        rate, pitch = phrase_prosody(phrase, liveliness)
        if rate_override:
            rate = rate_override
        if pitch_override:
            pitch = pitch_override

        communicate = edge_tts.Communicate(phrase, voice=voice, rate=rate, pitch=pitch)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                out.write(chunk["data"])

        if i < len(phrases) - 1:
            # между фразами — короткая пауза «как живой человек»
            gap = SILENCE_280MS if phrase.rstrip().endswith((".", "!", "…")) else SILENCE_150MS
            out.write(gap)

    return out.getvalue()


SPOKEN_STYLE_HINT = """
КАК ГОВОРИТЬ ВСЛУХ (важно для живого голоса):
- Пиши как по телефону: коротко, разговорно, без канцелярита.
- 1–2 короткие фразы, потом вопрос. Точки и запятые = паузы голоса.
- Можно мягкие связки: «смотрите», «поняла вас», «хорошо», «давайте так».
- Не лей воду. Не перечисляй через точку с запятой длинными абзацами.
""".strip()
