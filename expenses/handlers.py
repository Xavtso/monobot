"""
Expense tracker handlers.

Entry flow (state machine per user):
  user sends text → parse what we can → ask for each missing field one-by-one
  → save when complete

Draft dict stored in _drafts[user_id]:
  { category, amount, currency, date, step, chat_id, msg_id }

Steps:
  "awaiting_category"     – showing category keyboard
  "awaiting_currency"     – showing currency keyboard
  "awaiting_date"         – showing date keyboard
  "awaiting_date_manual"  – waiting for free-text date input
  "awaiting_new_category" – waiting for free-text new category name
"""
import logging
import re
from datetime import date

from telegram import Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters, ApplicationHandlerStop,
)

from expenses.db import ExpenseDB
from expenses.nbu import get_nbu_rate
from expenses.parser import DEFAULT_CATEGORIES, parse_expense, _parse_date
from expenses.keyboards import (
    add_category_keyboard, category_keyboard, confirm_delete_keyboard,
    currency_keyboard, date_keyboard, history_keyboard,
    main_menu_keyboard, stats_period_keyboard,
)
from expenses.formatter import (
    draft_status, format_categories, format_expense_for_delete,
    format_save_confirmation, format_stats,
)

logger = logging.getLogger(__name__)

_db: ExpenseDB | None = None

# Active drafts: user_id → draft dict
_drafts: dict[int, dict] = {}

PERIOD_DAYS   = {"month": 30, "year": 365, "all": None}
PERIOD_LABELS = {"month": "За місяць", "year": "За рік", "all": "За весь час"}

_DEL_RE = re.compile(r"^/del_(\d+)$")


# ── Draft helpers ─────────────────────────────────────────────────────────────

def _next_step(draft: dict, known_cats: list[str]) -> str | None:
    """Return the next field to ask for, or None if complete."""
    if not draft.get("category") or draft["category"] not in known_cats:
        return "category"
    if not draft.get("currency"):
        return "currency"
    if not draft.get("date"):
        return "date"
    return None


async def _ask_step(bot, chat_id: int, draft: dict, known_cats: list[str]):
    """Send or edit the draft message to ask for the next missing field."""
    step = draft.get("step", "")
    summary = draft_status(draft)

    if step == "awaiting_category":
        text = f"💳 *{summary}*\n\nЯка категорія?"
        kb = category_keyboard(known_cats)
    elif step == "awaiting_currency":
        text = f"💳 *{summary}*\n\nЯка валюта?"
        kb = currency_keyboard()
    elif step == "awaiting_date":
        text = f"💳 *{summary}*\n\nЯка дата?"
        kb = date_keyboard()
    elif step == "awaiting_date_manual":
        text = f"💳 *{summary}*\n\nВведи дату у форматі *ДД.ММ* або *ДД.ММ.РРРР*:"
        kb = None
    elif step == "awaiting_new_category":
        text = f"💳 *{summary}*\n\nНапиши назву нової категорії:"
        kb = None
    else:
        return

    msg_id = draft.get("msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=text, reply_markup=kb, parse_mode="Markdown",
            )
            return
        except Exception:
            pass  # message may have been deleted — fall through to send

    msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb,
                                 parse_mode="Markdown")
    draft["msg_id"] = msg.message_id


async def _advance_draft(bot, chat_id: int, user_id: int, draft: dict):
    """Figure out next step, ask, or save if complete."""
    known_cats = _db.get_all_categories(user_id)
    next_field = _next_step(draft, known_cats)

    if next_field is None:
        # All fields collected → save
        await _save_draft(bot, chat_id, user_id, draft)
        return

    draft["step"] = f"awaiting_{next_field}"
    await _ask_step(bot, chat_id, draft, known_cats)


async def _save_draft(bot, chat_id: int, user_id: int, draft: dict):
    """Fetch rate, save to DB, send confirmation, clear draft."""
    _drafts.pop(user_id, None)
    try:
        rate, source = await get_nbu_rate(draft["currency"], draft["date"])
    except ValueError as e:
        await bot.send_message(chat_id=chat_id, text=f"⚠️ {e}")
        return

    expense_id = _db.add_expense(
        user_id=user_id,
        expense_date=draft["date"],
        category=draft["category"],
        description=None,
        amount=draft["amount"],
        currency=draft["currency"],
        rate_uah=rate,
        amount_uah=draft["amount"] * rate,
        source=source,
    )
    text = format_save_confirmation(expense_id, draft, rate, source)
    msg_id = draft.get("msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=text, parse_mode="Markdown",
            )
            return
        except Exception:
            pass
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")


# ── Text message handler (group -1) ──────────────────────────────────────────

async def auto_expense_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 1. Skip if monobot has a pending classification question
    try:
        from handlers import _pending_classification as _mono_pending
        if user_id in _mono_pending:
            return
    except ImportError:
        pass

    # 2. Handle /del_N text command
    m = _DEL_RE.match(text)
    if m:
        expense_id = int(m.group(1))
        exp = _db.get_expense(expense_id, user_id)
        if exp:
            await update.message.reply_text(
                f"Видалити запис #{expense_id}?\n{format_expense_for_delete(exp)}",
                reply_markup=confirm_delete_keyboard(expense_id),
            )
            raise ApplicationHandlerStop
        return

    # 3. Intercept text input for active draft steps
    draft = _drafts.get(user_id)
    if draft:
        step = draft.get("step", "")

        if step == "awaiting_date_manual":
            parsed_date = _parse_date(text)
            if not parsed_date:
                await update.message.reply_text(
                    "❌ Не розпізнав дату. Напиши у форматі *ДД.ММ* або *ДД.ММ.РРРР*:",
                    parse_mode="Markdown",
                )
                raise ApplicationHandlerStop
            draft["date"] = parsed_date
            await update.message.delete()
            await _advance_draft(ctx.bot, update.effective_chat.id, user_id, draft)
            raise ApplicationHandlerStop

        if step == "awaiting_new_category":
            name = text.strip().capitalize()
            if not (2 <= len(name) <= 50):
                await update.message.reply_text("❌ Назва від 2 до 50 символів")
                raise ApplicationHandlerStop
            _db.add_category(user_id, name)
            draft["category"] = name
            await update.message.delete()
            await _advance_draft(ctx.bot, update.effective_chat.id, user_id, draft)
            raise ApplicationHandlerStop

        # User sends something new while a draft is active — start fresh
        new_parsed = parse_expense(text)
        if new_parsed:
            _drafts.pop(user_id, None)  # abandon old draft
            # fall through to step 4

    # 4. Try to parse as a new expense
    parsed = parse_expense(text)
    if not parsed:
        return  # not an expense — let monobot chat() handle it

    new_draft: dict = {
        "category": parsed["category"],
        "amount": parsed["amount"],
        "currency": parsed.get("currency"),   # may be None if not provided
        "date": parsed.get("date"),            # may be None if not provided
        "step": None,
        "chat_id": update.effective_chat.id,
        "msg_id": None,
    }

    # Strip defaults back to None so we ask about them
    if new_draft["currency"] == "UAH" and " UAH" not in text.upper():
        new_draft["currency"] = None  # wasn't explicit → ask
    if new_draft["date"] == date.today().isoformat() and not re.search(r'\d{1,2}\.\d{2}', text):
        new_draft["date"] = None  # wasn't explicit → ask

    _drafts[user_id] = new_draft
    await _advance_draft(ctx.bot, update.effective_chat.id, user_id, new_draft)
    raise ApplicationHandlerStop


# ── Callback handler ──────────────────────────────────────────────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    # ── Currency selection ─────────────────────────────────────────────────
    if data.startswith("exp_cur_"):
        draft = _drafts.get(user_id)
        if not draft:
            await query.edit_message_text("⏳ Сесія закінчилась. Надішли витрату ще раз.")
            return
        draft["currency"] = data[len("exp_cur_"):]
        draft["msg_id"] = query.message.message_id
        await _advance_draft(ctx.bot, chat_id, user_id, draft)

    # ── Date selection ─────────────────────────────────────────────────────
    elif data.startswith("exp_date_"):
        draft = _drafts.get(user_id)
        if not draft:
            await query.edit_message_text("⏳ Сесія закінчилась. Надішли витрату ще раз.")
            return
        value = data[len("exp_date_"):]
        if value == "manual":
            draft["step"] = "awaiting_date_manual"
            draft["msg_id"] = query.message.message_id
            await _ask_step(ctx.bot, chat_id, draft, _db.get_all_categories(user_id))
        else:
            draft["date"] = value  # YYYY-MM-DD from callback data
            draft["msg_id"] = query.message.message_id
            await _advance_draft(ctx.bot, chat_id, user_id, draft)

    # ── Category selection ─────────────────────────────────────────────────
    elif data.startswith("exp_cat_"):
        draft = _drafts.get(user_id)
        if not draft:
            await query.edit_message_text("⏳ Сесія закінчилась. Надішли витрату ще раз.")
            return
        value = data[len("exp_cat_"):]
        if value == "new":
            draft["step"] = "awaiting_new_category"
            draft["msg_id"] = query.message.message_id
            await _ask_step(ctx.bot, chat_id, draft, _db.get_all_categories(user_id))
        else:
            draft["category"] = value
            draft["msg_id"] = query.message.message_id
            await _advance_draft(ctx.bot, chat_id, user_id, draft)

    # ── Stats ──────────────────────────────────────────────────────────────
    elif data.startswith("exp_stats_"):
        period_key = data[len("exp_stats_"):]
        days = PERIOD_DAYS.get(period_key)
        label = PERIOD_LABELS.get(period_key, "За весь час")
        stats = _db.get_stats(user_id, days=days)
        await query.edit_message_text(
            format_stats(stats, label),
            reply_markup=stats_period_keyboard(period_key),
            parse_mode="Markdown",
        )

    # ── History ────────────────────────────────────────────────────────────
    elif data.startswith("exp_history_"):
        offset = int(data[len("exp_history_"):])
        expenses = _db.get_history(user_id, offset=offset, limit=10)
        total = _db.count_expenses(user_id)
        kb = history_keyboard(expenses, offset, total)
        header = "🗒 *Записи* — тисни щоб видалити\n" if expenses else ""
        text = header + ("" if expenses else "Немає записів")
        await query.edit_message_text(
            text or "🗒 *Записи* — тисни щоб видалити",
            reply_markup=kb,
            parse_mode="Markdown",
        )

    # ── Delete flow ────────────────────────────────────────────────────────
    elif data.startswith("exp_del_ask_"):
        expense_id = int(data[len("exp_del_ask_"):])
        exp = _db.get_expense(expense_id, user_id)
        if not exp:
            await query.edit_message_text("❌ Запис не знайдено")
            return
        await query.edit_message_text(
            f"Видалити запис #{expense_id}?\n{format_expense_for_delete(exp)}",
            reply_markup=confirm_delete_keyboard(expense_id),
        )

    elif data.startswith("exp_del_confirm_"):
        expense_id = int(data[len("exp_del_confirm_"):])
        deleted = _db.delete_expense(expense_id, user_id)
        # After deletion, show updated history
        expenses = _db.get_history(user_id, offset=0, limit=10)
        total = _db.count_expenses(user_id)
        kb = history_keyboard(expenses, 0, total)
        prefix = f"🗑 Запис #{expense_id} видалено\n\n" if deleted else f"❌ Запис #{expense_id} не знайдено\n\n"
        await query.edit_message_text(
            prefix + "🗒 *Записи* — тисни щоб видалити",
            reply_markup=kb,
            parse_mode="Markdown",
        )

    # ── Categories ─────────────────────────────────────────────────────────
    elif data == "exp_categories":
        custom = _db.get_custom_categories(user_id)
        await query.edit_message_text(
            format_categories(DEFAULT_CATEGORIES, custom),
            reply_markup=add_category_keyboard(),
            parse_mode="Markdown",
        )

    elif data == "exp_add_category":
        # Repurpose the "add category" flow outside of a draft
        # Store a sentinel draft-less state using _drafts with no amount
        _drafts[user_id] = {"__category_only": True, "msg_id": query.message.message_id,
                            "step": "awaiting_new_category", "chat_id": chat_id}
        await query.edit_message_text("Напиши назву нової категорії:")

    elif data == "exp_add":
        await query.edit_message_text(
            "Введи витрату в чат:\n\n"
            "_Готель 725.38 EUR 14.02_\n"
            "_Їжа 350_\n"
            "_Авіа 4500 01.04.2026_\n\n"
            "Бот запитає про всі пропущені поля 👇",
            parse_mode="Markdown",
        )


# ── Command handlers ──────────────────────────────────────────────────────────

async def expenses_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 *Трекер витрат*\n\n"
        "Або просто напиши витрату:\n"
        "_Готель 725.38 EUR 14.02_",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = _db.get_stats(update.effective_user.id)
    await update.message.reply_text(
        format_stats(stats, "За весь час"),
        reply_markup=stats_period_keyboard("all"),
        parse_mode="Markdown",
    )


async def history_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expenses = _db.get_history(user_id, offset=0, limit=10)
    total = _db.count_expenses(user_id)
    kb = history_keyboard(expenses, 0, total)
    await update.message.reply_text(
        "🗒 *Записи* — тисни щоб видалити" if expenses else "📋 Немає записів",
        reply_markup=kb,
        parse_mode="Markdown",
    )


# ── Registration ──────────────────────────────────────────────────────────────

def register_expense_handlers(app: Application):
    global _db

    try:
        from db import Database
        db_path = Database().path
    except Exception:
        import os
        db_path = os.path.join(os.getenv("DATA_DIR", "."), "monobot.db")

    _db = ExpenseDB(db_path)

    app.add_handler(CommandHandler(["expenses", "витрати"], expenses_menu))
    app.add_handler(CommandHandler(["статистика"], stats_cmd))
    app.add_handler(CommandHandler(["history", "історія"], history_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler, pattern=r"^exp_"))

    # group=-1 → runs before monobot chat handler (group 0)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, auto_expense_handler),
        group=-1,
    )

    logger.info("Expense tracker registered ✅")
