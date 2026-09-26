from __future__ import annotations

import json
import queue
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np
import sounddevice as sd
from rich.console import Console
from rich.live import Live
from rich.text import Text

from .config import ROOT

console = Console()

VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
VOSK_MODEL_DIR = ROOT / "models" / "vosk" / "vosk-model-small-ru-0.22"


def ensure_vosk_model() -> Path:
    if (VOSK_MODEL_DIR / "am" / "final.mdl").exists() or (VOSK_MODEL_DIR / "conf" / "model.conf").exists():
        return VOSK_MODEL_DIR

    VOSK_MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    zip_path = VOSK_MODEL_DIR.parent / "vosk-model-small-ru-0.22.zip"
    console.print("[dim]Скачиваю модель Vosk (русский, ~45 МБ) для live-распознавания…[/dim]")
    urlretrieve(VOSK_MODEL_URL, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(VOSK_MODEL_DIR.parent)
    zip_path.unlink(missing_ok=True)
    if not VOSK_MODEL_DIR.exists():
        # иногда папка уже с нужным именем
        matches = list(VOSK_MODEL_DIR.parent.glob("vosk-model-small-ru*"))
        if matches:
            return matches[0]
        raise FileNotFoundError("Не удалось распаковать модель Vosk")
    console.print("[green]Vosk готов[/green]")
    return VOSK_MODEL_DIR


class LiveSpeechToText:
    """Потоковое распознавание: текст появляется на экране, пока вы говорите."""

    def __init__(self, sample_rate: int = 16000):
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        model_path = ensure_vosk_model()
        console.print("[dim]Загружаю live-STT (Vosk)…[/dim]")
        self.model = Model(str(model_path))
        self.sample_rate = sample_rate
        self._Rec = KaldiRecognizer
        console.print("[green]Live-распознавание готово[/green]")

    def listen_until_silence(
        self,
        silence_sec: float = 0.9,
        max_record_sec: float = 15.0,
        energy_threshold: float = 0.012,
        min_speech_sec: float = 0.35,
    ) -> tuple[str, np.ndarray]:
        recognizer = self._Rec(self.model, self.sample_rate)
        recognizer.SetWords(True)

        block = int(self.sample_rate * 0.05)  # 50 ms
        silence_needed = max(1, int(silence_sec / 0.05))
        max_blocks = int(max_record_sec / 0.05)
        min_speech_blocks = int(min_speech_sec / 0.05)

        q: queue.Queue[np.ndarray | None] = queue.Queue()

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            q.put(indata.copy())

        final_parts: list[str] = []
        frames: list[np.ndarray] = []
        partial = ""
        silent_blocks = 0
        speech_seen = 0
        started = False

        display = Text.from_markup("[cyan]Слушаю…[/cyan] [dim]говорите[/dim]")
        with Live(display, console=console, refresh_per_second=12, transient=False) as live:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=block,
                callback=callback,
            ):
                for _ in range(max_blocks):
                    try:
                        data = q.get(timeout=1.0)
                    except queue.Empty:
                        continue
                    if data is None:
                        break

                    mono = data.reshape(-1)
                    frames.append(mono.copy())
                    energy = float(np.sqrt(np.mean(mono**2)))
                    pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()

                    if recognizer.AcceptWaveform(pcm):
                        result = json.loads(recognizer.Result())
                        text = (result.get("text") or "").strip()
                        if text:
                            final_parts.append(text)
                            partial = ""
                    else:
                        part = json.loads(recognizer.PartialResult())
                        partial = (part.get("partial") or "").strip()

                    shown = (" ".join(final_parts) + (" " + partial if partial else "")).strip()
                    if shown:
                        live.update(
                            Text.assemble(
                                ("Вы: ", "bold yellow"),
                                (shown, "yellow"),
                            )
                        )
                    else:
                        live.update(Text.from_markup("[cyan]Слушаю…[/cyan] [dim]говорите[/dim]"))

                    if energy >= energy_threshold:
                        started = True
                        speech_seen += 1
                        silent_blocks = 0
                    elif started:
                        silent_blocks += 1
                        if speech_seen >= min_speech_blocks and silent_blocks >= silence_needed:
                            break

        # финальный кусок
        tail = json.loads(recognizer.FinalResult())
        tail_text = (tail.get("text") or "").strip()
        if tail_text:
            final_parts.append(tail_text)

        merged: list[str] = []
        for p in final_parts:
            if not merged or merged[-1] != p:
                merged.append(p)
        text = " ".join(merged).strip()
        audio = np.concatenate(frames).astype(np.float32) if frames else np.zeros(0, dtype=np.float32)
        if text:
            console.print(f"[bold yellow]Вы:[/bold yellow] {text}")
        else:
            console.print("[bold yellow]Вы:[/bold yellow] [dim][тишина][/dim]")
        return text, audio
