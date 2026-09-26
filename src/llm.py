from __future__ import annotations

from typing import Any

import httpx
from rich.console import Console

console = Console()


class OllamaChat:
    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float,
        timeout_sec: float,
        num_predict: int = 80,
        num_ctx: int = 2048,
        keep_alive: str = "30m",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout_sec
        self.num_predict = num_predict
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.messages: list[dict[str, str]] = []

    def set_system(self, system_prompt: str) -> None:
        self.messages = [{"role": "system", "content": system_prompt}]

    def _options(self) -> dict[str, Any]:
        import os

        n = int(os.environ.get("OLLAMA_NUM_THREAD") or os.cpu_count() or 8)
        return {
            "temperature": self.temperature,
            "num_predict": self.num_predict,
            "num_ctx": self.num_ctx,
            "num_thread": max(1, n),
            "num_gpu": 0,
            "num_batch": int(os.environ.get("OLLAMA_NUM_BATCH", "512")),
        }

    def ensure_alive(self) -> None:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            r.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                "Ollama не отвечает на http://127.0.0.1:11434.\n"
                "Установите: https://ollama.com/download\n"
                "Затем: ollama pull qwen2.5:3b && ollama serve"
            ) from exc

        models = [m.get("name", "") for m in r.json().get("models", [])]
        short = self.model.split(":")[0]
        if not any(self.model in name or name.startswith(short) for name in models):
            raise RuntimeError(
                f"Модель '{self.model}' не найдена в Ollama.\n"
                f"Установите: ollama pull {self.model}\n"
                f"Доступно: {models or 'пусто'}"
            )

    def warmup(self) -> None:
        """Держит модель в RAM — первый ответ в диалоге быстрее."""
        console.print("[dim]Прогрев Ollama...[/dim]")
        payload = {
            "model": self.model,
            "prompt": "ок",
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {**self._options(), "num_predict": 1},
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                client.post(f"{self.base_url}/api/generate", json=payload).raise_for_status()
            console.print("[green]Ollama готова[/green]")
        except Exception as exc:
            console.print(f"[yellow]Прогрев пропущен: {exc}[/yellow]")

    def chat(self, user_text: str, style_hint: str | None = None) -> str:
        self.messages.append({"role": "user", "content": user_text})
        history = self.messages[:1] + self.messages[1:][-8:]
        if style_hint:
            history = list(history)
            history[-1] = {
                "role": "user",
                "content": (
                    f"{user_text}\n\n"
                    f"(Служебная подсказка стиля — не упоминай клиенту и не цитируй):\n{style_hint}"
                ),
            }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": history,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": self._options(),
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        reply = data.get("message", {}).get("content", "").strip()
        self.messages.append({"role": "assistant", "content": reply})
        return reply
