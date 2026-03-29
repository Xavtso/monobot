CURRENCY_SYMBOLS = {"UAH": "₴", "EUR": "€", "USD": "$", "GBP": "£", "PLN": "zł"}


def _fmt(amount: float) -> str:
    """Format number with space as thousands separator: 37 012.53"""
    return f"{amount:,.2f}".replace(",", "\u00a0")  # non-breaking space


def _date(date_str: str) -> str:
    """Convert YYYY-MM-DD to DD.MM.YYYY."""
    try:
        y, m, d = date_str.split("-")
        return f"{d}.{m}.{y}"
    except Exception:
        return date_str


def _date_short(date_str: str) -> str:
    """DD.MM"""
    try:
        _, m, d = date_str.split("-")
        return f"{d}.{m}"
    except Exception:
        return date_str


def format_save_confirmation(expense_id: int, parsed: dict, rate: float, source: str) -> str:
    sym = CURRENCY_SYMBOLS.get(parsed["currency"], parsed["currency"])
    amount_uah = parsed["amount"] * rate
    lines = [
        f"✅ Збережено \\#{expense_id}",
        "",
        f"📅 {_date(parsed['date'])}",
        f"🏷 {parsed['category']}",
        f"💰 {_fmt(parsed['amount'])} {parsed['currency']}",
    ]
    if parsed["currency"] != "UAH":
        lines.append(f"📈 Курс НБУ: 1 {parsed['currency']} = {_fmt(rate)} грн")
        lines.append(f"💵 Разом: {_fmt(amount_uah)} грн")
    lines += ["", f"/del\\_{expense_id} — скасувати"]
    return "\n".join(lines)


def format_stats(stats: dict, period_label: str = "За весь час") -> str:
    if stats["count"] == 0:
        return "📊 Немає витрат за вказаний період"

    lines = [
        "📊 Статистика витрат",
        "",
        f"{period_label}:",
        f"├ Транзакцій: {stats['count']}",
        f"├ Загалом: {_fmt(stats['total'])} грн",
        f"└ Середня: {_fmt(stats['avg'])} грн",
    ]

    if stats["by_currency"]:
        lines += ["", "За валютами:"]
        for i, row in enumerate(stats["by_currency"]):
            sym = CURRENCY_SYMBOLS.get(row["currency"], row["currency"])
            conn = "└" if i == len(stats["by_currency"]) - 1 else "├"
            lines.append(f"{conn} {row['currency']}: {_fmt(row['total'])} {sym}")

    if stats["by_category"]:
        lines += ["", "За категоріями:"]
        for i, row in enumerate(stats["by_category"]):
            conn = "└" if i == len(stats["by_category"]) - 1 else "├"
            lines.append(f"{conn} {row['category']:<12} {_fmt(row['total'])} грн")

    return "\n".join(lines)


def format_history(expenses: list) -> str:
    if not expenses:
        return "📋 Немає записів"

    lines = ["📋 Останні записи:", ""]
    for exp in expenses:
        sym = CURRENCY_SYMBOLS.get(exp["currency"], exp["currency"])
        lines.append(
            f"#{exp['id']}  {_date_short(exp['expense_date'])}  "
            f"{exp['category']:<12}  "
            f"{_fmt(exp['amount'])} {sym}  "
            f"{_fmt(exp['amount_uah'])} грн"
        )
    return "\n".join(lines)


def format_categories(default_cats: list, custom_cats: list) -> str:
    lines = ["Категорії:", "", f"Стандартні: {', '.join(default_cats)}"]
    if custom_cats:
        lines.append(f"Кастомні: {', '.join(custom_cats)}")
    return "\n".join(lines)


def format_expense_for_delete(exp: dict) -> str:
    return (
        f"{exp['category']} · "
        f"{_fmt(exp['amount'])} {exp['currency']} · "
        f"{_date(exp['expense_date'])}"
    )
