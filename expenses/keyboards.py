from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Додати витрату", callback_data="exp_add")],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="exp_stats_all"),
            InlineKeyboardButton("📋 Категорії", callback_data="exp_categories"),
        ],
        [InlineKeyboardButton("🗑 Останній запис", callback_data="exp_last")],
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


def confirm_delete_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Так, видалити", callback_data=f"exp_del_confirm_{expense_id}"),
        InlineKeyboardButton("❌ Скасувати", callback_data="exp_del_cancel"),
    ]])


def history_keyboard(offset: int, total: int, page_size: int = 10) -> InlineKeyboardMarkup | None:
    if offset + page_size >= total:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("← Ще", callback_data=f"exp_history_{offset + page_size}")
    ]])


def add_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("➕ Нова категорія", callback_data="exp_add_category")
    ]])
