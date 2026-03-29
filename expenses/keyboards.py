from datetime import date, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

CURRENCY_SYMBOLS = {"UAH": "₴", "EUR": "€", "USD": "$", "GBP": "£", "PLN": "zł"}


def currency_keyboard() -> InlineKeyboardMarkup:
    pairs = [("UAH", "₴"), ("EUR", "€"), ("USD", "$"), ("GBP", "£"), ("PLN", "zł")]
    buttons = [InlineKeyboardButton(f"{c} {s}", callback_data=f"exp_cur_{c}") for c, s in pairs]
    return InlineKeyboardMarkup([buttons[:3], buttons[3:]])


def date_keyboard() -> InlineKeyboardMarkup:
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Сьогодні",                callback_data=f"exp_date_{today.isoformat()}"),
            InlineKeyboardButton("Вчора",                   callback_data=f"exp_date_{yesterday.isoformat()}"),
            InlineKeyboardButton(day_before.strftime("%d.%m"), callback_data=f"exp_date_{day_before.isoformat()}"),
        ],
        [InlineKeyboardButton("✏️ Ввести дату вручну", callback_data="exp_date_manual")],
    ])


def category_keyboard(categories: list[str]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(cat, callback_data=f"exp_cat_{cat}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("➕ Нова категорія", callback_data="exp_cat_new")])
    return InlineKeyboardMarkup(rows)


def history_keyboard(expenses: list, offset: int, total: int,
                     page_size: int = 10) -> InlineKeyboardMarkup | None:
    """Each expense row is a tappable button (tap to delete). Paging at the bottom."""
    rows = []
    for exp in expenses:
        sym = CURRENCY_SYMBOLS.get(exp["currency"], exp["currency"])
        d = exp["expense_date"][5:].replace("-", ".")  # MM-DD → MM.DD
        label = f"🗑 #{exp['id']}  {d}  {exp['category']}  {exp['amount']:.0f} {sym}"
        rows.append([InlineKeyboardButton(label, callback_data=f"exp_del_ask_{exp['id']}")])
    if offset + page_size < total:
        rows.append([InlineKeyboardButton("← Ще", callback_data=f"exp_history_{offset + page_size}")])
    return InlineKeyboardMarkup(rows) if rows else None


def confirm_delete_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Так, видалити", callback_data=f"exp_del_confirm_{expense_id}"),
        InlineKeyboardButton("❌ Ні",            callback_data=f"exp_history_0"),
    ]])


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Додати витрату", callback_data="exp_add")],
        [
            InlineKeyboardButton("📊 Статистика",  callback_data="exp_stats_all"),
            InlineKeyboardButton("📋 Категорії",   callback_data="exp_categories"),
        ],
        [InlineKeyboardButton("🗒 Історія",        callback_data="exp_history_0")],
    ])


def stats_period_keyboard(current: str = "all") -> InlineKeyboardMarkup:
    periods = [("За місяць", "month"), ("За рік", "year"), ("За весь час", "all")]
    buttons = [
        InlineKeyboardButton(
            f"▶ {label}" if key == current else label,
            callback_data=f"exp_stats_{key}"
        )
        for label, key in periods
    ]
    return InlineKeyboardMarkup([buttons])


def add_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("➕ Нова категорія", callback_data="exp_add_category")
    ]])
