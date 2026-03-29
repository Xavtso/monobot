import logging
import re

from telegram import Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

from expenses.db import ExpenseDB
from expenses.nbu import get_nbu_rate
from expenses.parser import DEFAULT_CATEGORIES, parse_expense
from expenses.keyboards import (
    add_category_keyboard, confirm_delete_keyboard,
    history_keyboard, main_menu_keyboard, stats_period_keyboard,
)
from expenses.formatter import (
    format_categories, format_expense_for_delete,
    format_history, format_save_confirmation, format_stats,
)

logger = logging.getLogger(__name__)

_db: ExpenseDB | None = None

# user_id → True when bot is waiting for a new category name
_waiting_category: dict[int, bool] = {}

PERIOD_DAYS   = {"month": 30, "year": 365, "all": None}
PERIOD_LABELS = {"month": "За місяць", "year": "За рік", "all": "За весь час"}

_DEL_RE = re.compile(r"^/del_(\d+)$")


# ── Commands ──────────────────────────────────────────────────────────────────

async def expenses_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 *Трекер витрат*\n\n"
        "Вибери дію або введи витрату одним рядком:\n"
        "_Готель 725.38 EUR 14.02_",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = _db.get_stats(update.effective_user.id)
    await update.message.reply_text(
        format_stats(stats, "За весь час"),
        reply_markup=stats_period_keyboard("all"),
    )


async def history_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expenses = _db.get_history(user_id, offset=0, limit=10)
    total = _db.count_expenses(user_id)
    await update.message.reply_text(
        format_history(expenses),
        reply_markup=history_keyboard(0, total),
    )


# ── Auto-detect expense from plain text ───────────────────────────────────────

async def auto_expense_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 1. Waiting for a new category name?
    if _waiting_category.pop(user_id, False):
        name = text.strip().capitalize()
        if not (2 <= len(name) <= 50):
            await update.message.reply_text("❌ Назва від 2 до 50 символів")
        else:
            _db.add_category(user_id, name)
            await update.message.reply_text(f"✅ Категорія *{name}* додана", parse_mode="Markdown")
        return  # stop — don't let monobot chat() also respond

    # 2. /del_N shortcut
    m = _DEL_RE.match(text)
    if m:
        expense_id = int(m.group(1))
        exp = _db.get_expense(expense_id, user_id)
        if exp:
            await update.message.reply_text(
                f"Видалити запис \\#{expense_id}?\n{format_expense_for_delete(exp)}",
                reply_markup=confirm_delete_keyboard(expense_id),
                parse_mode="MarkdownV2",
            )
        else:
            await update.message.reply_text(f"❌ Запис #{expense_id} не знайдено")
        return

    # 3. Skip if monobot has a pending classification question for this user
    try:
        from handlers import _pending_classification as _mono_pending
        if user_id in _mono_pending:
            return
    except ImportError:
        pass

    # 4. Try to parse as expense
    parsed = parse_expense(text)
    if not parsed:
        return  # not an expense — let monobot chat() handle it

    try:
        rate, source = await get_nbu_rate(parsed["currency"], parsed["date"])
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return

    expense_id = _db.add_expense(
        user_id=user_id,
        expense_date=parsed["date"],
        category=parsed["category"],
        description=None,
        amount=parsed["amount"],
        currency=parsed["currency"],
        rate_uah=rate,
        amount_uah=parsed["amount"] * rate,
        source=source,
    )
    await update.message.reply_text(
        format_save_confirmation(expense_id, parsed, rate, source),
        parse_mode="MarkdownV2",
    )
    # Raise to stop monobot chat() from also firing on this message
    from telegram.ext import ApplicationHandlerStop
    raise ApplicationHandlerStop


# ── Callbacks ─────────────────────────────────────────────────────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "exp_add":
        await query.edit_message_text(
            "Введи витрату в чат:\n\n"
            "_Готель 725.38 EUR 14.02_\n"
            "_Їжа 350_\n"
            "_Авіа 4500 UAH 01.04.2026_\n\n"
            "Формат: *Категорія Сума \\[Валюта\\] \\[ДД\\.ММ\\]*",
            parse_mode="MarkdownV2",
        )

    elif data.startswith("exp_stats_"):
        period_key = data[len("exp_stats_"):]
        days = PERIOD_DAYS.get(period_key)
        label = PERIOD_LABELS.get(period_key, "За весь час")
        stats = _db.get_stats(user_id, days=days)
        await query.edit_message_text(
            format_stats(stats, label),
            reply_markup=stats_period_keyboard(period_key),
        )

    elif data == "exp_categories":
        custom = _db.get_custom_categories(user_id)
        text = format_categories(DEFAULT_CATEGORIES, custom)
        await query.edit_message_text(text, reply_markup=add_category_keyboard())

    elif data == "exp_add_category":
        _waiting_category[user_id] = True
        await query.edit_message_text("Надішли назву нової категорії:")

    elif data == "exp_last":
        last_id = _db.get_last_expense_id(user_id)
        if not last_id:
            await query.edit_message_text("❌ Немає записів")
            return
        exp = _db.get_expense(last_id, user_id)
        await query.edit_message_text(
            f"Видалити останній запис \\#{last_id}?\n{format_expense_for_delete(exp)}",
            reply_markup=confirm_delete_keyboard(last_id),
            parse_mode="MarkdownV2",
        )

    elif data.startswith("exp_del_confirm_"):
        expense_id = int(data[len("exp_del_confirm_"):])
        deleted = _db.delete_expense(expense_id, user_id)
        await query.edit_message_text(
            f"🗑 Запис #{expense_id} видалено" if deleted
            else f"❌ Запис #{expense_id} не знайдено"
        )

    elif data == "exp_del_cancel":
        await query.edit_message_text("✅ Скасовано")

    elif data.startswith("exp_history_"):
        offset = int(data[len("exp_history_"):])
        expenses = _db.get_history(user_id, offset=offset, limit=10)
        total = _db.count_expenses(user_id)
        await query.edit_message_text(
            format_history(expenses),
            reply_markup=history_keyboard(offset, total),
        )


# ── Registration ──────────────────────────────────────────────────────────────

def register_expense_handlers(app: Application):
    global _db

    # Reuse the same SQLite file as the main bot
    try:
        from db import Database
        db_path = Database().path
    except Exception:
        import os
        db_path = os.path.join(os.getenv("DATA_DIR", "."), "monobot.db")

    _db = ExpenseDB(db_path)

    # Commands
    app.add_handler(CommandHandler(["expenses", "витрати"], expenses_menu))
    app.add_handler(CommandHandler(["статистика"], stats_cmd))
    app.add_handler(CommandHandler(["history", "історія"], history_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(callback_handler, pattern=r"^exp_"))

    # Text auto-detection — group -1 runs before monobot chat handler (group 0)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, auto_expense_handler),
        group=-1,
    )

    logger.info("Expense tracker registered ✅")
