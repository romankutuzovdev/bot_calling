#!/usr/bin/env python3
"""Быстрая проверка окружения MVP."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from rich.console import Console

from src.config import load_config

console = Console()


def main() -> int:
    cfg = load_config()
    console.print("[bold]Проверка MVP[/bold]")
    console.print(f"  продукт: {cfg['product']['name']}")
    console.print(f"  модель:  {cfg['ollama']['model']}")

    url = cfg["ollama"]["base_url"].rstrip("/") + "/api/tags"
    try:
        r = httpx.get(url, timeout=3.0)
        r.raise_for_status()
        models = [m.get("name") for m in r.json().get("models", [])]
        console.print(f"  [green]Ollama OK[/green] · модели: {models or 'нет'}")
        wanted = cfg["ollama"]["model"]
        if not any(wanted in (m or "") for m in models):
            console.print(f"  [yellow]Нужно:[/yellow] ollama pull {wanted}")
            return 2
    except Exception:
        console.print("  [red]Ollama не запущена[/red]")
        console.print("  1) Установите https://ollama.com/download")
        console.print("  2) Откройте приложение Ollama")
        console.print(f"  3) ollama pull {cfg['ollama']['model']}")
        return 1

    console.print("[green]Готово к запуску:[/green] python -m src.main --mode text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
