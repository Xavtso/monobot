from expenses.keyboards import CURRENCY_SYMBOLS


def _fmt(amount: float) -> str:
    """37012.53 → '37 012.53' (non-breaking space)"""
    return f"{amount:,.2f}".replace(",", "\u00a0")


def _date(date_str: str) -> str:
    """YYYY-MM-DD → DD.MM.YYYY"""
    try:
        y, m, d = date_str.split("-")
        return f"{d}.{m}.{y}"
    except Exception:
        return date_str


def _date_short(date_str: str) -> str:
    """YYYY-MM-DD → DD.MM"""
    try:
        _, m, d = date_str.split("-")
        return f"{d}.{m}"
    except Exception:
        return date_str


def draft_status(draft: dict) -> str:
    """One-line summary of what's been collected so far."""
    parts = []
    if draft.get("category"):
        parts.append(draft["category"])
    if draft.get("amount"):
        parts.append(_fmt(draft["amount"]))
    if draft.get("currency") and draft["currency"] != "UAH":
        parts.append(draft["currency"])
    elif draft.get("currency") == "UAH":
        parts.append("₴")
    if draft.get("date"):
        parts.append(_date_short(draft["date"]))
    return "  ·  ".join(parts) if parts else "—"


def format_save_confirmation(expense_id: int, draft: dict, rate: float, source: str) -> str:
    sym = CURRENCY_SYMBOLS.get(draft["currency"], draft["currency"])
    amount_uah = draft["amount"] * rate
    lines = [
        f"✅ *Збережено #{expense_id}*",
        "",
        f"📅 {_date(draft['date'])}",
        f"🏷 {draft['category']}",
        f"💰 {_fmt(draft['amount'])} {draft['currency']}",
    ]
    if draft["currency"] != "UAH":
        lines.append(f"📈 Курс НБУ: 1 {draft['currency']} = {_fmt(rate)} грн  _{source}_")
        lines.append(f"💵 {_fmt(amount_uah)} грн")
    lines += ["", f"/del\\_{expense_id} — скасувати"]
    return "\n".join(lines)


def format_stats(stats: dict, period_label: str = "За весь час") -> str:
    if stats["count"] == 0:
        return "📊 Немає витрат за вказаний період"

    lines = [
        "📊 *Статистика витрат*",
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
            c = "└" if i == len(stats["by_currency"]) - 1 else "├"
            lines.append(f"{c} {row['currency']}: {_fmt(row['total'])} {sym}")
    if stats["by_category"]:
        lines += ["", "За категоріями:"]
        for i, row in enumerate(stats["by_category"]):
            c = "└" if i == len(stats["by_category"]) - 1 else "├"
            lines.append(f"{c} {row['category']:<12} {_fmt(row['total'])} грн")
    return "\n".join(lines)


def format_expense_for_delete(exp: dict) -> str:
    sym = CURRENCY_SYMBOLS.get(exp["currency"], exp["currency"])
    return (
        f"{exp['category']} · {_fmt(exp['amount'])} {sym} · {_date(exp['expense_date'])}"
    )


def format_categories(default_cats: list, custom_cats: list) -> str:
    lines = ["*Категорії:*", "", f"Стандартні: {', '.join(default_cats)}"]
    if custom_cats:
        lines.append(f"Кастомні: {', '.join(custom_cats)}")
    return "\n".join(lines)
