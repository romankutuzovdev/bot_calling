from __future__ import annotations

import os
import subprocess
import tempfile
import warnings
import wave
from functools import lru_cache
from pathlib import Path

from rich.console import Console

from .config import ROOT, ensure_tmp

# Нужно для загрузки XTTS без интерактива
os.environ.setdefault("COQUI_TOS_AGREED", "1")
# На Windows Server без GPU — не трогаем CUDA
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
warnings.filterwarnings("ignore", message=".*torchaudio.*torchcodec.*")
warnings.filterwarnings("ignore", message=".*torchcodec.*")

console = Console()
_xtts = None


def _clean(text: str) -> str:
    return " ".join(text.replace("END_CALL", "").replace("CLOSE_DEAL", "").split())


def speak(
    text: str,
    voice: str = "Milena",
    rate: str | int = 200,
    engine: str = "piper",
    model_path: str | None = None,
    speaker_wav: str | None = None,
) -> None:
    """Локальный TTS: piper | clone (XTTS) | macos."""
    clean = _clean(text)
    if not clean:
        return

    engine = (engine or "piper").lower()
    if engine in ("clone", "xtts"):
        _speak_clone(clean, speaker_wav=speaker_wav)
        return
    if engine == "piper":
        _speak_piper(clean, model_path=model_path)
        return
    if engine in ("macos", "say"):
        _speak_macos(clean, voice=voice or "Milena", rate=rate)
        return
    if engine == "edge":
        _speak_edge(clean, voice=voice, rate=str(rate))
        return

    console.print(f"[yellow]Неизвестный TTS engine={engine}, пробую Piper[/yellow]")
    _speak_piper(clean, model_path=model_path)


def warmup_clone(speaker_wav: str | None = None) -> None:
    """Предзагрузка XTTS при старте бота."""
    _resolve_speaker(speaker_wav)  # проверка файла
    console.print("[dim]Загружаю XTTS (клон голоса)…[/dim]")
    _get_xtts()
    console.print("[green]Клон голоса готов[/green]")


def _resolve_speaker(speaker_wav: str | None) -> Path:
    candidates = []
    if speaker_wav:
        p = Path(speaker_wav)
        candidates.append(p if p.is_absolute() else ROOT / p)
    candidates.extend(
        [
            ROOT / "voices" / "my_voice_22k.wav",
            ROOT / "voices" / "my_voice.wav",
        ]
    )
    for ref in candidates:
        if ref.exists():
            return ref
    raise FileNotFoundError(
        "Нет сэмпла голоса. Запишите: python -m src.record_voice\n"
        "Ожидается voices/my_voice.wav"
    )


def _get_xtts():
    global _xtts
    if _xtts is None:
        from TTS.api import TTS  # type: ignore

        # Явно CPU (на Mac MPS с XTTS нестабилен; на сервере без GPU — тоже CPU).
        # Позже на NVIDIA: TTS(..., gpu=True) или CUDA torch.
        console.print("[dim]Загрузка XTTS v2 на CPU (первый раз долго)…[/dim]")
        _xtts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)
    return _xtts


def synthesize_clone_wav(
    text: str,
    speaker_wav: str | None = None,
    language: str = "ru",
) -> Path:
    """Генерирует WAV клоном голоса (XTTS, CPU). Возвращает путь к файлу."""
    clean = _clean(text)
    if not clean:
        raise ValueError("Пустой текст для TTS")
    ref = _resolve_speaker(speaker_wav)
    tts = _get_xtts()
    ensure_tmp()
    out = ensure_tmp() / "clone_out.wav"
    console.print(f"[dim]XTTS CPU → {ref.name}: «{clean[:60]}…»[/dim]")
    tts.tts_to_file(
        text=clean,
        file_path=str(out),
        speaker_wav=str(ref),
        language=language,
    )
    return out


def synthesize_clone_bytes(
    text: str,
    speaker_wav: str | None = None,
    language: str = "ru",
) -> bytes:
    """То же, что synthesize_clone_wav, но байты WAV для HTTP."""
    path = synthesize_clone_wav(text, speaker_wav=speaker_wav, language=language)
    return path.read_bytes()


def clone_status(speaker_wav: str | None = None) -> dict:
    """Статус клона: есть ли сэмпл, загружена ли модель."""
    try:
        ref = _resolve_speaker(speaker_wav)
        speaker_ok = True
        speaker_path = str(ref)
    except FileNotFoundError as exc:
        speaker_ok = False
        speaker_path = str(exc)
    return {
        "engine": "clone",
        "device": "cpu",
        "speaker_ok": speaker_ok,
        "speaker_path": speaker_path,
        "model_loaded": _xtts is not None,
        "note": "На CPU фраза обычно 20–90 сек. На быстром сервере — ближе к нижней границе.",
    }


def _speak_clone(text: str, speaker_wav: str | None) -> None:
    try:
        out = synthesize_clone_wav(text, speaker_wav=speaker_wav)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    except Exception as exc:
        console.print(f"[red]XTTS недоступен: {exc}[/red]\nПадаю на Piper.")
        _speak_piper(text)
        return
    subprocess.run(["afplay", str(out)], check=False)


def _resolve_piper_model(model_path: str | None) -> Path:
    if model_path:
        p = Path(model_path)
        if not p.is_absolute():
            p = ROOT / p
        if p.exists():
            return p
    default = ROOT / "models" / "piper" / "ru_RU-denis-medium.onnx"
    if default.exists():
        return default
    matches = list((ROOT / "models" / "piper").rglob("*.onnx"))
    if matches:
        return matches[0]
    raise FileNotFoundError(
        "Piper-модель не найдена. Скачайте:\n"
        "  python -m piper.download_voices ru_RU-denis-medium --download-dir models/piper"
    )


@lru_cache(maxsize=2)
def _load_piper(model: str):
    from piper import PiperVoice

    return PiperVoice.load(model)


def _speak_piper(text: str, model_path: str | None = None) -> None:
    model = _resolve_piper_model(model_path)
    voice = _load_piper(str(model))
    ensure_tmp()
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=ensure_tmp(), delete=False) as tmp:
        out_path = Path(tmp.name)
    try:
        with wave.open(str(out_path), "wb") as wf:
            voice.synthesize_wav(text, wf)
        subprocess.run(["afplay", str(out_path)], check=False)
    finally:
        out_path.unlink(missing_ok=True)


def _say_rate(rate: str | int | float) -> int:
    if isinstance(rate, (int, float)):
        return max(120, min(300, int(rate)))
    s = str(rate).strip()
    if s.endswith("%"):
        try:
            pct = float(s.replace("%", "").replace("+", ""))
            return max(120, min(300, int(175 * (1 + pct / 100))))
        except ValueError:
            return 200
    try:
        return max(120, min(300, int(float(s))))
    except ValueError:
        return 200


def _speak_macos(text: str, voice: str, rate: str | int) -> None:
    wpm = _say_rate(rate)
    result = subprocess.run(
        ["say", "-v", voice, "-r", str(wpm), text],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        subprocess.run(["say", "-v", "Milena", "-r", str(wpm), text], check=False)


def _speak_edge(text: str, voice: str, rate: str) -> None:
    import asyncio

    import edge_tts

    ensure_tmp()
    with tempfile.NamedTemporaryFile(suffix=".mp3", dir=ensure_tmp(), delete=False) as tmp:
        out_path = Path(tmp.name)

    async def _synth() -> None:
        await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(out_path))

    try:
        asyncio.run(_synth())
        subprocess.run(["afplay", str(out_path)], check=False)
    finally:
        out_path.unlink(missing_ok=True)


def speak_from_config(text: str, tts_cfg: dict) -> None:
    speak(
        text,
        voice=tts_cfg.get("voice", "Milena"),
        rate=tts_cfg.get("rate", 200),
        engine=tts_cfg.get("engine", "piper"),
        model_path=tts_cfg.get("model"),
        speaker_wav=tts_cfg.get("speaker_wav"),
    )
