import random
from datetime import datetime


CATEGORY_COMMENTS = {
    "☕ Кафе/Ресторани": [
        "ще одна кава",
        "бариста вже знає твоє ім'я?",
        "кофеїнова залежність задокументована",
        "може вдома зварити?",
    ],
    "🍔 Фастфуд": [
        "тіло-сміттєвий бак активовано",
        "здорове харчування поставлено на паузу",
        "макдак знову переміг",
        "вдруге за тиждень",
    ],
    "🍺 Бари": [
        "інвестиція в похмілля",
        "рішення які здаються мудрими після третього",
        "завтра пошкодуєш",
    ],
    "🛒 Супермаркет": [
        "сподіваємось не тільки чіпси",
        "базова потреба",
        "класика",
    ],
    "🚕 Таксі": [
        "ноги є, але таксі крутіше",
        "метро — для слабаків?",
        "транспортна незалежність коштує",
    ],
    "💅 Краса": [
        "краса вимагає жертв (фінансових)",
        "виглядати добре — дорого",
    ],
    "🎮 Розваги": [
        "гроші за щастя — чесна угода",
        "відпочинок теж коштує",
    ],
    "💡 Підписки": [
        "ти точно цим користуєшся?",
        "ще одна підписка яку забудеш відмінити",
        "тихий вбивця бюджету",
    ],
    "⛽ АЗС": [
        "машина їсть не менше за тебе",
        "нафта не дешевшає",
    ],
    "🚬 Тютюн/Алкоголь": [
        "підписка на проблеми зі здоров'ям",
        "лікарі скажуть дякую потім",
    ],
    "👗 Одяг": [
        "але ж є що вдягнути...",
        "шопінг-терапія — дорогий лікар",
    ],
}

DEFAULT_COMMENTS = [
    "гроші пішли",
    "баланс впав",
    "витрата зафіксована",
]


def get_comment(category: str, amount: float) -> str:
    comments = CATEGORY_COMMENTS.get(category, DEFAULT_COMMENTS)
    comment = random.choice(comments)
    if amount > 1000:
        comment += " 💀"
    elif amount > 500:
        comment += " 😬"
    return comment


def format_notification(
    tx: dict,
    category: str,
    monthly_total: int,
    monthly_count: int,
    pattern_alerts: list[str] | None = None,
) -> str:
    amount = abs(tx.get("amount", 0)) / 100
    balance = tx.get("balance", 0) / 100
    description = tx.get("description", "")
    comment_text = tx.get("comment", "")

    ts = tx.get("time", 0)
    hour = datetime.fromtimestamp(ts).hour if ts else 0
    time_emoji = "🌙" if hour >= 22 or hour < 6 else "🌆" if hour >= 18 else "☀️"

    monthly_sum = monthly_total / 100

    lines = [
        f"💸 *{amount:,.0f}₴*  ·  {description}",
        f"{category}  ·  {time_emoji} баланс {balance:,.0f}₴",
    ]

    if comment_text:
        lines.append(f"📝 {comment_text}")

    lines.append("")
    cat_name = category.split(" ", 1)[-1].lower() if " " in category else category.lower()
    lines.append(f"Цього місяця {cat_name}: {monthly_sum:,.0f}₴ ({monthly_count}×)")
    lines.append(f"_{get_comment(category, amount)}_")

    if pattern_alerts:
        lines.append("")
        for alert in pattern_alerts:
            lines.append(f"⚠️ {alert}")

    return "\n".join(lines)
