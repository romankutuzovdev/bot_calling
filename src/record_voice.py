"""Запись вашего голоса для будущего клонирования (15–30 сек)."""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from rich.console import Console
from rich.panel import Panel

from .config import ROOT

console = Console()

SCRIPT_LINES = [
    "Алло, здравствуйте! Меня зовут Максим, компания AutoKit Import.",
    "Мы привозим машинокомплекты из США и Англии под вашу модель.",
    "Двигатели, коробки, кузовные части — с проверкой и доставкой.",
    "Сегодня могу зафиксировать слот на подбор без предоплаты.",
    "Назовите марку, модель и год автомобиля — и я всё посчитаю.",
]


def record_seconds(seconds: float, sample_rate: int = 22050) -> np.ndarray:
    console.print(f"[cyan]Идёт запись {seconds:.0f} сек… говорите[/cyan]")
    audio = sd.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio.reshape(-1)


def save_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # нормализация
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = np.clip(audio / peak * 0.9, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def main() -> int:
    out = ROOT / "voices" / "my_voice.wav"
    sample_rate = 22050
    duration = 25.0

    console.print(
        Panel.fit(
            "[bold]Запись голоса[/bold]\n"
            "Piper сам по себе голос не клонирует — эта запись нужна для XTTS позже.\n"
            "Сейчас сохраним чистый сэмпл ~25 секунд."
        )
    )
    console.print("Прочитайте вслух (спокойно, без шума):\n")
    for i, line in enumerate(SCRIPT_LINES, 1):
        console.print(f"  {i}. {line}")

    console.input("\n[bold]Enter[/bold] — начать запись… ")
    audio = record_seconds(duration, sample_rate)
    save_wav(out, audio, sample_rate)

    # Нормализация под XTTS
    ffmpeg = ROOT / ".tmp" / "bin" / "ffmpeg"
    out_22k = ROOT / "voices" / "my_voice_22k.wav"
    if ffmpeg.exists():
        import subprocess

        subprocess.run(
            [str(ffmpeg), "-y", "-i", str(out), "-ar", "22050", "-ac", "1", "-sample_fmt", "s16", str(out_22k)],
            check=False,
            capture_output=True,
        )
        console.print(f"[green]Для клона:[/green] {out_22k}")

    console.print(f"\n[green]Сохранено:[/green] {out}")
    console.print("Прослушать: afplay voices/my_voice.wav")
    console.print("\n[dim]Запуск бота вашим голосом: ./scripts/call_me.sh[/dim]")

    import subprocess

    subprocess.run(["afplay", str(out)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
