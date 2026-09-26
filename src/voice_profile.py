from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from rich.console import Console

console = Console()


@dataclass
class VoiceProfile:
    gender: str = "unknown"  # male | female | unknown
    emotion: str = "neutral"  # calm | engaged | tense | neutral
    tempo: str = "medium"  # slow | medium | fast
    pitch_hz: float = 0.0
    energy: float = 0.0
    speech_ratio: float = 0.0

    def label_ru(self) -> str:
        g = {"male": "мужской", "female": "женский", "unknown": "неясно"}.get(self.gender, self.gender)
        e = {
            "calm": "спокойный",
            "engaged": "вовлечённый",
            "tense": "напряжённый",
            "neutral": "нейтральный",
        }.get(self.emotion, self.emotion)
        t = {"slow": "медленный", "medium": "средний", "fast": "быстрый"}.get(self.tempo, self.tempo)
        return f"пол≈{g} · эмоция≈{e} · темп≈{t}"

    def style_instruction(self) -> str:
        """Мягкая подстройка стиля для LLM (не жёсткие факты о человеке)."""
        parts = [
            "Подстрой стиль ответа под голос собеседника (это эвристика, не утверждай пол/возраст вслух):"
        ]
        if self.gender == "female":
            parts.append("- Тон чуть мягче и аккуратнее, без грубого давления.")
        elif self.gender == "male":
            parts.append("- Тон деловой и прямой, без лишней «воды».")

        if self.emotion == "tense":
            parts.append("- Собеседник звучит напряжённо: извинись коротко, снизь давление, один мягкий вопрос.")
        elif self.emotion == "engaged":
            parts.append("- Собеседник вовлечён: можно чуть быстрее к сути и к следующему шагу.")
        elif self.emotion == "calm":
            parts.append("- Собеседник спокоен: спокойный темп, без агрессивного дожима.")

        if self.tempo == "fast":
            parts.append("- Говорит быстро: отвечай очень коротко (1 фраза + 1 вопрос).")
        elif self.tempo == "slow":
            parts.append("- Говорит медленно: не торопи, формулировки простые, без пачки вопросов.")

        parts.append("- Не говори клиенту, что анализируешь его голос.")
        return "\n".join(parts)


def _estimate_pitch_hz(audio: np.ndarray, sample_rate: int) -> float:
    """Грубая оценка F0 через автокорреляцию (без librosa)."""
    if audio.size < sample_rate // 5:
        return 0.0
    # берём середину фразы
    mid = len(audio) // 2
    win = audio[max(0, mid - sample_rate // 2) : mid + sample_rate // 2]
    if win.size < 1024:
        win = audio
    # нормализация
    win = win - float(np.mean(win))
    peak = float(np.max(np.abs(win))) or 1.0
    win = win / peak

    min_lag = int(sample_rate / 350)  # ~350 Hz
    max_lag = int(sample_rate / 70)  # ~70 Hz
    if max_lag >= len(win):
        return 0.0

    # автокорреляция на нужном диапазоне
    corr_best = -1.0
    lag_best = 0
    for lag in range(min_lag, max_lag):
        a = win[:-lag]
        b = win[lag:]
        c = float(np.dot(a, b) / (len(a) + 1e-9))
        if c > corr_best:
            corr_best = c
            lag_best = lag
    if lag_best <= 0 or corr_best < 0.2:
        return 0.0
    return float(sample_rate / lag_best)


def analyze_voice(audio: np.ndarray, sample_rate: int = 16000) -> VoiceProfile:
    if audio is None or audio.size == 0:
        return VoiceProfile()

    mono = audio.astype(np.float32).reshape(-1)
    energy = float(np.sqrt(np.mean(mono**2)))
    # доля «речи» по энергии
    frame = int(sample_rate * 0.02)
    if frame < 1:
        frame = 1
    energies = []
    for i in range(0, len(mono) - frame, frame):
        chunk = mono[i : i + frame]
        energies.append(float(np.sqrt(np.mean(chunk**2))))
    if not energies:
        return VoiceProfile(energy=energy)

    thr = max(0.01, float(np.median(energies)) * 1.3)
    speech_frames = sum(1 for e in energies if e >= thr)
    speech_ratio = speech_frames / max(1, len(energies))

    pitch = _estimate_pitch_hz(mono, sample_rate)

    # пол по pitch (эвристика)
    if pitch <= 0:
        gender = "unknown"
    elif pitch < 160:
        gender = "male"
    elif pitch > 185:
        gender = "female"
    else:
        gender = "unknown"

    # темп: сколько «речевых» кадров относительно длины
    duration = len(mono) / sample_rate
    # speech_ratio высокий + короткие паузы ≈ быстро
    if speech_ratio > 0.72 and duration < 6:
        tempo = "fast"
    elif speech_ratio < 0.45 or duration > 10:
        tempo = "slow"
    else:
        tempo = "medium"

    # эмоция: энергия + вариативность
    var = float(np.std(energies)) if energies else 0.0
    if energy > 0.08 and var > 0.04:
        emotion = "tense" if pitch > 200 or var > 0.07 else "engaged"
    elif energy < 0.03:
        emotion = "calm"
    else:
        emotion = "neutral"

    return VoiceProfile(
        gender=gender,
        emotion=emotion,
        tempo=tempo,
        pitch_hz=round(pitch, 1),
        energy=round(energy, 4),
        speech_ratio=round(speech_ratio, 3),
    )


def merge_profiles(prev: VoiceProfile | None, new: VoiceProfile) -> VoiceProfile:
    """Сглаживаем профиль по ходу звонка (не прыгаем на каждой фразе)."""
    if prev is None or prev.gender == "unknown":
        return new
    gender = new.gender if new.gender != "unknown" else prev.gender
    # эмоцию и темп обновляем осторожно
    emotion = new.emotion if new.emotion != "neutral" else prev.emotion
    tempo = new.tempo if new.tempo != "medium" else prev.tempo
    return VoiceProfile(
        gender=gender,
        emotion=emotion,
        tempo=tempo,
        pitch_hz=new.pitch_hz or prev.pitch_hz,
        energy=new.energy,
        speech_ratio=new.speech_ratio,
    )


def print_profile(profile: VoiceProfile) -> None:
    console.print(f"[magenta]Голос:[/magenta] {profile.label_ru()}  [dim](F0≈{profile.pitch_hz} Hz)[/dim]")
