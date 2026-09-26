from __future__ import annotations

import time
from typing import Callable

import numpy as np
import sounddevice as sd
from rich.console import Console

console = Console()


def record_until_silence(
    sample_rate: int,
    channels: int,
    silence_sec: float,
    max_record_sec: float,
    energy_threshold: float,
    min_speech_sec: float,
    should_stop: Callable[[], bool] | None = None,
) -> np.ndarray:
    """Запись с микрофона до паузы после речи (простой energy VAD)."""
    block = int(sample_rate * 0.05)  # 50 ms
    silence_needed = int(silence_sec / 0.05)
    max_blocks = int(max_record_sec / 0.05)
    min_speech_blocks = int(min_speech_sec / 0.05)

    frames: list[np.ndarray] = []
    silent_blocks = 0
    speech_seen = 0
    started = False

    console.print("[cyan]Слушаю... говорите[/cyan] (тишина — стоп, Ctrl+C — выход)")

    with sd.InputStream(samplerate=sample_rate, channels=channels, dtype="float32") as stream:
        for _ in range(max_blocks):
            if should_stop and should_stop():
                break
            data, _ = stream.read(block)
            mono = data.reshape(-1)
            energy = float(np.sqrt(np.mean(mono**2)))
            frames.append(mono.copy())

            if energy >= energy_threshold:
                started = True
                speech_seen += 1
                silent_blocks = 0
            elif started:
                silent_blocks += 1
                if speech_seen >= min_speech_blocks and silent_blocks >= silence_needed:
                    break

    if not frames:
        return np.zeros(0, dtype=np.float32)

    audio = np.concatenate(frames).astype(np.float32)
    # Обрезаем хвост тишины
    trim = int(silence_sec * sample_rate * 0.5)
    if trim > 0 and len(audio) > trim:
        audio = audio[:-trim]
    return audio


def warmup_mic(sample_rate: int = 16000, seconds: float = 0.3) -> None:
    """Короткий прогрев устройства ввода (на macOS иногда помогает)."""
    try:
        sd.rec(int(sample_rate * seconds), samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()
    except Exception:
        time.sleep(0.1)
