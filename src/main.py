from __future__ import annotations

import argparse
import re
import sys

from rich.console import Console
from rich.panel import Panel

from .config import load_config
from .llm import OllamaChat
from .prompts import build_opening, build_system_prompt, clean_for_speech
from .tts import speak_from_config, warmup_clone
from .voice_profile import VoiceProfile, analyze_voice, merge_profiles, print_profile

console = Console()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Голосовой ИИ-продавец (симулятор звонка)")
    p.add_argument("--mode", choices=["voice", "text"], default=None)
    p.add_argument("--mock", action="store_true", help="Скрипт без Ollama")
    p.add_argument("--config", default=None)
    return p.parse_args()


def mock_reply(user_text: str, turn: int, scenario: str = "sales") -> str:
    t = user_text.lower()
    if any(x in t for x in ("не звоните", "отстаньте", "удалите")):
        return "Понял, извините за беспокойство. Всего доброго. END_CALL"

    if scenario in ("logistics", "logistics_qualify"):
        if any(x in t for x in ("не звоните", "не актуально", "больше не звоните")):
            return "Поняла вас. Хорошего дня! END_CALL"
        if any(x in t for x in ("нет перевозок", "ничего не нужно", "не надо", "не интересно")) and turn >= 3:
            return "Поняла вас. Тогда не буду отвлекать. Хорошего дня! END_CALL"
        if turn <= 1 and any(x in t for x in ("да", "удобно", "слушаю", "говорите", "минуту")):
            return "Мы занимаемся грузовыми перевозками по Беларуси, России, СНГ, Европе, Турции и Китаю. Подскажите, вы сами занимаетесь организацией перевозок или лучше связаться с человеком, который отвечает за логистику?"
        if any(x in t for x in ("неудобно", "занят", "перезвон")):
            return "Понимаю. Подскажите, когда будет удобнее перезвонить — сегодня позже или завтра?"
        if any(x in t for x in ("удобно", "минуту", "говорите", "давай")) and turn <= 3:
            return "Мы занимаемся грузовыми перевозками по Беларуси, России, СНГ, Европе, Турции и Китаю. Подскажите, вы сами занимаетесь организацией перевозок или лучше связаться с человеком, который отвечает за логистику?"
        if any(x in t for x in ("логист", "я отвечаю", "я занимаюсь", "директор", "снабжен")):
            return "Подскажите, пожалуйста, вы сейчас пользуетесь услугами сторонних транспортных компаний?"
        if any(x in t for x in ("есть перевозчик", "пользуемся", "да возим", "сторонн")):
            return "Поняла. А какие направления для вас сейчас наиболее актуальны?"
        if any(x in t for x in ("москва", "европ", "турц", "китай", "беларус", "росси", "снг", "казах")):
            return "И как часто примерно возникают перевозки — несколько раз в месяц, каждую неделю или чаще?"
        if any(x in t for x in ("раз в", "недел", "месяц", "часто", "регуляр")):
            return "Поняла вас. Мы можем быть дополнительным перевозчиком и оперативно считать стоимость. Куда удобнее отправить информацию — WhatsApp, Telegram или на почту?"
        if any(x in t for x in ("whatsapp", "ватсап", "телеграм", "telegram", "почт", "email", "@")):
            return "Отлично. Зафиксирую и передам менеджеру. Он свяжется и предметно обсудит перевозку. Спасибо, хорошего дня! CLOSE_DEAL"
        if "почт" in t:
            return "Конечно. Чтобы отправить полезную информацию, какие направления перевозок для вас наиболее актуальны?"
        return "Подскажите, вы сами занимаетесь организацией перевозок или лучше связаться с человеком по логистике?"

    if any(x in t for x in ("не надо", "не интересно")) and turn >= 2:
        return "Хорошо, не буду отнимать время. Если понадобится комплект — наберите. END_CALL"
    if any(x in t for x in ("дорого", "цена", "сколько")):
        return "Обычно от двух тысяч восьмисот долларов под ключ. Какая у вас марка и год?"
    if any(x in t for x in ("подумаю", "потом", "занят", "перезвон")):
        return "Ок, тогда просто зафиксируем бесплатную заявку. Какая машина?"
    if re.search(r"\b(bmw|бмв|toyota|тойота|audi|ауди|mercedes|мерседес|kia|киа)\b", t) or "год" in t:
        return "Принял. Нужен двигатель, коробка или кузов? Могу сразу поставить в подбор."
    if any(x in t for x in ("да", "давай", "слушаю", "минуту", "интересно", "заявк", "бронь")):
        if turn <= 1:
            return "Отлично. Какая марка и год автомобиля?"
        return "Супер, заявку фиксирую без оплаты. Перезвоним с вариантами. Договорились? CLOSE_DEAL"
    if "почт" in t:
        return "Пришлю, но сначала марка и год — иначе будет общая вода. Назовите машину?"
    return "Мы подбираем комплекты из США и Англии. Какая у вас марка и год?"


def strip_flags(reply: str) -> tuple[str, str | None]:
    flag = None
    # метки только если явно в конце / отдельным словом
    if re.search(r"\bCLOSE_DEAL\b", reply):
        flag = "CLOSE_DEAL"
    elif re.search(r"\bEND_CALL\b", reply):
        # не завершаем, если это явно продолжение разговора с вопросом
        spoken_preview = clean_for_speech(reply)
        if "?" in spoken_preview and not any(
            x in spoken_preview.lower() for x in ("всего доброго", "до свидания", "не буду беспокоить")
        ):
            flag = None
        else:
            flag = "END_CALL"
    return clean_for_speech(reply), flag


def shorten_reply(text: str, max_chars: int = 220) -> str:
    if len(text) <= max_chars:
        return text
    # обрезаем по предложениям
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for p in parts:
        if not p:
            continue
        if sum(len(x) for x in out) + len(p) > max_chars and out:
            break
        out.append(p)
        if len(out) >= 2:
            break
    return " ".join(out) if out else text[:max_chars]


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config) if args.config else load_config()
    mode = args.mode or cfg.get("modes", {}).get("default", "voice")
    agent_name = cfg["agent"]["name"]

    system = build_system_prompt(cfg)
    use_mock = bool(args.mock)
    llm = None
    if not use_mock:
        llm = OllamaChat(
            base_url=cfg["ollama"]["base_url"],
            model=cfg["ollama"]["model"],
            temperature=cfg["ollama"]["temperature"],
            timeout_sec=cfg["ollama"]["timeout_sec"],
            num_predict=int(cfg["ollama"].get("num_predict", 70)),
            num_ctx=int(cfg["ollama"].get("num_ctx", 2048)),
            keep_alive=str(cfg["ollama"].get("keep_alive", "30m")),
        )

    console.print(
        Panel.fit(
            f"[bold]Звонок · {cfg['agent']['company']}[/bold]\n"
            f"Голос: Microsoft Edge · модель: {cfg['ollama']['model'] if not use_mock else 'mock'}"
        )
    )

    if not use_mock:
        assert llm is not None
        try:
            llm.ensure_alive()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        llm.set_system(system)
        llm.warmup()

    stt = None
    live_stt = None
    if mode == "voice":
        from .audio_io import warmup_mic
        from .live_stt import LiveSpeechToText

        a = cfg["audio"]
        use_live = bool(a.get("live", True))
        try:
            if use_live:
                live_stt = LiveSpeechToText(sample_rate=a.get("sample_rate", 16000))
            else:
                raise RuntimeError("live disabled")
        except Exception as exc:
            console.print(f"[yellow]Live-STT недоступен ({exc}), обычный Whisper[/yellow]")
            from .audio_io import record_until_silence
            from .stt import SpeechToText

            w = cfg["whisper"]
            stt = SpeechToText(
                model_size=w["model_size"],
                device=w["device"],
                compute_type=w["compute_type"],
                language=w["language"],
                cpu_threads=int(w.get("cpu_threads", 4)),
            )
        warmup_mic(a.get("sample_rate", 16000))
        if str(cfg.get("tts", {}).get("engine", "")).lower() in ("clone", "xtts"):
            try:
                warmup_clone(cfg["tts"].get("speaker_wav"))
            except Exception as exc:
                console.print(f"[yellow]Клон недоступен ({exc})[/yellow]")

    opening = build_opening(cfg)
    # Чтобы модель продолжала диалог, а не здоровалась снова
    if llm is not None:
        llm.messages.append({"role": "assistant", "content": opening})

    console.print(f"\n[bold green]{agent_name}:[/bold green] {opening}")
    if mode == "voice":
        speak_from_config(opening, cfg["tts"])

    empty_streak = 0
    voice_profile: VoiceProfile | None = None
    profile_enabled = bool(cfg.get("voice_profile", {}).get("enabled", True))
    max_turns = int(cfg["agent"].get("max_turns", 16))
    for turn in range(1, max_turns + 1):
        console.print(f"\n[cyan]Ваша очередь — говорите[/cyan]  [dim](ход {turn}/{max_turns}, Ctrl+C — сброс)[/dim]")
        audio = None
        try:
            if mode == "text":
                user_text = console.input("[bold yellow]Вы:[/bold yellow] ").strip()
            else:
                a = cfg["audio"]
                if live_stt is not None:
                    user_text, audio = live_stt.listen_until_silence(
                        silence_sec=a["silence_sec"],
                        max_record_sec=a["max_record_sec"],
                        energy_threshold=a["energy_threshold"],
                        min_speech_sec=a["min_speech_sec"],
                    )
                else:
                    from .audio_io import record_until_silence

                    assert stt is not None
                    audio = record_until_silence(
                        sample_rate=a["sample_rate"],
                        channels=a["channels"],
                        silence_sec=a["silence_sec"],
                        max_record_sec=a["max_record_sec"],
                        energy_threshold=a["energy_threshold"],
                        min_speech_sec=a["min_speech_sec"],
                    )
                    console.print("[dim]Слушаю → текст…[/dim]")
                    user_text = stt.transcribe(audio, a["sample_rate"])
                    console.print(f"[bold yellow]Вы:[/bold yellow] {user_text or '[тишина]'}")
        except KeyboardInterrupt:
            bye = "Хорошо, всего доброго, до свидания."
            console.print(f"\n[bold green]{agent_name}:[/bold green] {bye}")
            if mode == "voice":
                speak_from_config(bye, cfg["tts"])
            return 0

        style_hint = None
        if profile_enabled and mode == "voice" and audio is not None and getattr(audio, "size", 0) > 0:
            sample_rate = int(cfg.get("audio", {}).get("sample_rate", 16000))
            instant = analyze_voice(audio, sample_rate)
            voice_profile = merge_profiles(voice_profile, instant)
            print_profile(voice_profile)
            style_hint = voice_profile.style_instruction()

        if not user_text:
            empty_streak += 1
            ask = "Алло, плохо слышно. Повторите, пожалуйста?"
            console.print(f"[bold green]{agent_name}:[/bold green] {ask}")
            if mode == "voice":
                speak_from_config(ask, cfg["tts"])
            if empty_streak >= 3:
                console.print("[yellow]Тишина слишком долго — завершаю звонок[/yellow]")
                return 0
            continue
        empty_streak = 0

        lower = user_text.lower()
        if any(x in lower for x in ("пока", "до свидания", "сбрось", "положить трубку", "exit", "quit")):
            bye = "Хорошо, всего доброго, до свидания."
            console.print(f"[bold green]{agent_name}:[/bold green] {bye}")
            if mode == "voice":
                speak_from_config(bye, cfg["tts"])
            return 0

        if use_mock:
            scenario = str(cfg.get("scenario") or cfg.get("agent", {}).get("style") or "sales")
            reply = mock_reply(user_text, turn, scenario=scenario)
        else:
            assert llm is not None
            console.print("[dim]Думаю…[/dim]")
            try:
                reply = llm.chat(user_text, style_hint=style_hint)
            except Exception as exc:
                console.print(f"[red]Ошибка LLM: {exc}[/red]")
                return 1

        spoken, flag = strip_flags(reply)
        spoken = shorten_reply(spoken)
        if not spoken:
            spoken = "Поняла вас. Подскажите, пожалуйста, удобно буквально минуту?"

        # если модель забыла метку, а клиент явно согласился на контакт
        if flag is None and any(
            x in lower
            for x in (
                "заявк",
                "оставляй",
                "давай бронь",
                "договорились",
                "оформляй",
                "считай",
                "расчёт",
                "расчет",
                "whatsapp",
                "ватсап",
                "телеграм",
                "telegram",
                "почта",
                "email",
                "@",
                "передай менеджер",
                "пусть перезвон",
            )
        ):
            if any(
                x in spoken.lower()
                for x in (
                    "заявк",
                    "зафиксир",
                    "оставля",
                    "принял",
                    "хорошо",
                    "супер",
                    "отлично",
                    "расчёт",
                    "расчет",
                    "менеджер",
                    "передам",
                    "отправ",
                )
            ):
                flag = "CLOSE_DEAL"
                if "менеджер" not in spoken.lower() and "заявк" not in spoken.lower():
                    spoken = "Отлично. Зафиксирую и передам менеджеру. Он свяжется с вами. Спасибо, хорошего дня!"

        console.print(f"[bold green]{agent_name}:[/bold green] {spoken}")
        if mode == "voice":
            speak_from_config(spoken, cfg["tts"])

        if flag == "CLOSE_DEAL":
            console.print("[bold green]✓ Заявка / сделка зафиксирована[/bold green]")
            return 0
        if flag == "END_CALL":
            console.print("[yellow]Звонок завершён[/yellow]")
            return 0

    wrap = "Ладно, не буду занимать линию. Если понадобится подбор — наберите. Всего доброго."
    console.print(f"[bold green]{agent_name}:[/bold green] {wrap}")
    if mode == "voice":
        speak_from_config(wrap, cfg["tts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
