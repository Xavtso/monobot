from datetime import datetime


CATEGORY_COMMENTS = {
    "☕ Кафе/Ресторани": [
        "ще одна кава якої ти 'заслуговуєш'",
        "кофеїнова залежність задокументована",
        "бариста тебе вже по імені знає?",
    ],
    "🍔 Фастфуд": [
        "тіло — храм, але сьогодні він їсть бургер",
        "здорове харчування сьогодні відпочиває",
        "макдак знову переміг",
    ],
    "🍺 Бари": [
        "інвестиція в соціальний капітал",
        "рішення які здаються мудрими після третього",
        "завтра буде важко",
    ],
    "🛒 Супермаркет": [
        "їжа — базова потреба, ок",
        "сподіваємось не тільки чіпси",
        "класика жанру",
    ],
    "🚕 Таксі": [
        "ноги є але таксі крутіше",
        "транспортна незалежність коштує грошей",
        "метро — для слабаків?",
    ],
    "💅 Краса": [
        "інвестиція в себе — це окей",
        "виглядати добре — дорого",
        "краса вимагає жертв (фінансових)",
    ],
    "🎮 Розваги": [
        "гроші за щастя — чесна угода",
        "відпочинок теж коштує",
        "головне щоб було весело",
    ],
    "💡 Підписки": [
        "ти точно цим користуєшся?",
        "ще одна підписка яку забудеш відмінити",
        "регулярне списання — тихий вбивця бюджету",
    ],
    "⛽ АЗС": [
        "машина їсть не менше за тебе",
        "нафта не дешевшає",
        "класика автовласника",
    ],
    "🚬 Тютюн/Алкоголь": [
        "прем'єр підписка на проблеми зі здоров'ям",
        "це хобі з преміум-підпискою",
        "лікарі скажуть дякую потім",
    ],
    "👗 Одяг": [
        "шафа знову поповнилась",
        "але є ж що вдягнути...",
        "шопінг-терапія — дорогий лікар",
    ],
}

DEFAULT_COMMENTS = [
    "гроші пішли",
    "баланс впав",
    "витрата зафіксована",
]


def get_comment(category: str, amount: float) -> str:
    import random
    comments = CATEGORY_COMMENTS.get(category, DEFAULT_COMMENTS)
    comment = random.choice(comments)

    if amount > 1000:
        comment += " 💀"
    elif amount > 500:
        comment += " 😬"

    return comment


def format_notification(tx: dict, category: str, monthly_total: int, monthly_count: int) -> str:
    amount = abs(tx.get("amount", 0)) / 100
    balance = tx.get("balance", 0) / 100
    description = tx.get("description", "")
    comment_text = tx.get("comment", "")

    ts = tx.get("time", 0)
    hour = datetime.fromtimestamp(ts).hour if ts else 0
    time_emoji = "🌙" if hour >= 22 or hour < 6 else "🌆" if hour >= 18 else "☀️"

    monthly_sum = monthly_total / 100

    lines = [
        f"💸 {amount:,.0f}₴  ·  {description}",
        f"{category}  ·  {time_emoji} баланс {balance:,.0f}₴",
    ]

    if comment_text:
        lines.append(f"📝 {comment_text}")

    lines.append("")
    lines.append(f"Цього місяця на {category.split()[-1].lower()}: {monthly_sum:,.0f}₴ ({monthly_count} разів)")
    lines.append(f"_{get_comment(category, amount)}_")

    return "\n".join(lines)
