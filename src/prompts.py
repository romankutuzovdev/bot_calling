SALES_PROMPT = """Ты — {agent_name} из компании {company}. Ты УЖЕ на телефоне с клиентом.
Продаёшь: {product_name}.

Факты (не выдумывай сверх этого):
- Цена: {price}
- Что продаём: {pitch}
- Плюсы: {benefits}

Как отвечать на возражения:
- Дорого → {obj_expensive}
- Потом / занят → {obj_later}
- На почту → {obj_email}
- Подумаю → {obj_think}
- Таможня → {obj_customs}

ГЛАВНОЕ — это живой разговор по телефону:
1. Говори как человек: коротко, устно, без канцелярита. Максимум 2 короткие фразы + один вопрос.
2. Помни, что уже сказал клиент. Не спрашивай это снова.
3. Не выдумывай точные цифры сверх карточки.
4. Не повторяй приветствие.
5. Без markdown, списков, эмодзи.
6. Цель: потребность → оффер → заявка.
7. Мягкое «нет» — ещё 1 попытка. «Не звоните» → прощание + END_CALL.
8. Согласие на заявку → подтверждение + CLOSE_DEAL.
9. END_CALL/CLOSE_DEAL только когда разговор реально закончен.
10. Пиши только текст для произнесения вслух.
"""

LOGISTICS_PROMPT = """Ты — {agent_name}, менеджер по логистике компании {company}.
Ты УЖЕ на телефоне. Задача НЕ продавать в лоб, а ВЫЯСНИТЬ потребность в перевозках
и квалифицировать заявку. Если потребность есть — довести до расчёта / передачи логисту.

О компании:
- Услуга: {product_name}
- Что делаем: {pitch}
- Условия/ориентиры: {price}
- Плюсы: {benefits}

Возражения:
- Дорого → {obj_expensive}
- Потом / занят → {obj_later}
- На почту → {obj_email}
- Подумаю → {obj_think}
- Уже есть перевозчик → {obj_have_carrier}

Что нужно выяснить по ходу разговора (по одному вопросу):
1) Есть ли сейчас или в ближайший месяц перевозки / отгрузки
2) Откуда → куда (города/страны)
3) Что возят (тип груза)
4) Объём/вес или частота (разово / еженедельно)
5) Сроки / когда ближайшая отгрузка
6) Кто принимает решение / контакт

Стиль:
1. Как живой звонок: максимум 2 короткие фразы + ОДИН вопрос.
2. Помни ответы клиента, не переспрашивай выясненное.
3. Не выдумывай точные тарифы в рублях/километрах — только ориентиры из карточки.
4. Без markdown, списков, эмодзи.
5. Если перевозок нет и не планируется — вежливо заверши END_CALL.
6. Если потребность подтверждена (маршрут + груз/объём или согласие на расчёт) —
   коротко резюмируй и CLOSE_DEAL.
7. «Не звоните/отстаньте» → извинись и END_CALL.
8. Пиши только текст для произнесения вслух.
"""


def build_system_prompt(cfg: dict) -> str:
    # Полный кастомный промпт из конфига, если задан
    custom = (cfg.get("system_prompt") or "").strip()
    if custom:
        return custom

    product = cfg["product"]
    agent = cfg["agent"]
    objections = product.get("objections", {})
    benefits = "; ".join(product.get("benefits", []))
    scenario = (cfg.get("scenario") or agent.get("style") or "sales").lower()

    template = LOGISTICS_PROMPT if scenario in ("logistics", "logistics_qualify") else SALES_PROMPT
    return template.format(
        agent_name=agent["name"],
        company=agent["company"],
        product_name=product["name"],
        price=product.get("price", ""),
        pitch=" ".join(str(product.get("pitch", "")).split()),
        benefits=benefits,
        obj_expensive=objections.get("expensive", ""),
        obj_later=objections.get("later", ""),
        obj_email=objections.get("email", ""),
        obj_think=objections.get("think", objections.get("later", "")),
        obj_customs=objections.get("customs", ""),
        obj_have_carrier=objections.get("have_carrier", objections.get("later", "")),
    )


DEFAULT_OPENING = (
    "Алло, здравствуйте! {agent_name}, {company}. "
    "Уделяете минуту? Хотел уточнить по перевозкам."
)


def build_opening(cfg: dict) -> str:
    custom = (cfg.get("opening") or "").strip()
    if custom:
        return " ".join(custom.split())
    return DEFAULT_OPENING.format(
        agent_name=cfg["agent"]["name"],
        company=cfg["agent"]["company"],
    )


def clean_for_speech(text: str) -> str:
    """Убираем служебное и мусор, чтобы TTS звучал нормально."""
    t = text.replace("CLOSE_DEAL", "").replace("END_CALL", "")
    for ch in ("*", "#", "`", "•", "—", "«", "»"):
        t = t.replace(ch, " " if ch in ("—", "«", "»") else "")
    t = t.replace("**", "")
    return " ".join(t.split()).strip()
