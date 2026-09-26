from __future__ import annotations

import numpy as np
from faster_whisper import WhisperModel
from rich.console import Console

console = Console()


class SpeechToText:
    def __init__(
        self,
        model_size: str,
        device: str,
        compute_type: str,
        language: str,
        cpu_threads: int = 4,
    ):
        console.print(f"[dim]Загружаю Whisper ({model_size})...[/dim]")
        self.language = language
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )
        console.print("[green]Whisper готов[/green]")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if audio.size == 0:
            return ""
        peak = float(np.max(np.abs(audio)))
        if peak > 0:
            audio = audio / peak * 0.9

        segments, _info = self.model.transcribe(
            audio,
            language=self.language,
            vad_filter=False,
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
            without_timestamps=True,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text
