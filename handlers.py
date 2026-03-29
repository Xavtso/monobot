import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from monobank import MonobankClient
from db import Database
from classifier import Classifier, VALID_CATEGORIES
from analytics import Analytics
from patterns import get_pattern_summary
from privat_csv import parse_privat_csv, PrivatCSVError
from user_context import get_owner

logger = logging.getLogger(__name__)

# In-memory: maps telegram_user_id → tx_id awaiting classification reply
_pending_classification: dict[int, str] = {}

# In-memory: queue of tx_ids remaining from /reclassify manual review
_reclassify_queue: dict[int, list[str]] = {}


def set_pending(user_id: int, tx_id: str):
    """Register a pending classification reply for a user. Called by webhook."""
    _pending_classification[user_id] = tx_id


def setup(db: Database, mono: MonobankClient, classifier: Classifier,
          analytics: Analytics, mono_partner=None, partner_label: str = "партнер"):
    """Return a dict of handler coroutines bound to the given services."""
    from datetime import datetime as _dt

    async def _ask_next_reclassify(bot, chat_id: int, user_id: int):
        """Send the next unclassified tx from the reclassify queue to the user."""
        queue = _reclassify_queue.get(user_id, [])
        if not queue:
            await bot.send_message(chat_id, "✅ Всі розібрали!\n/categories — переглянути")
            return
        tx_id = queue[0]
        tx = db.get_transaction_by_id(tx_id)
        if not tx:
            queue.pop(0)
            await _ask_next_reclassify(bot, chat_id, user_id)
            return
        _pending_classification[user_id] = tx_id

        dt = _dt.fromtimestamp(tx["time"]) if tx.get("time") else None
        date_str = dt.strftime("%d.%m.%Y %H:%M") if dt else "—"
        amount_str = f"{abs(tx['amount']) / 100:.0f}₴"
        desc = tx.get("description") or "—"
        comment = tx.get("comment") or ""
        mcc = tx.get("mcc") or 0
        remaining = len(queue)

        lines = [
            f"❓ *{desc}*",
            f"💸 {amount_str}  ·  📅 {date_str}",
        ]
        if comment:
            lines.append(f"💬 {comment}")
        if mcc:
            lines.append(f"MCC: {mcc}")
        lines.append(f"\nНапиши категорію або *пропустити*")
        lines.append(f"_Залишилось: {remaining}_")

        await bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    def _help_keyboard() -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton("🔄 Синк Mono",       callback_data="help_sync"),
                InlineKeyboardButton("📊 Статистика",       callback_data="help_stats"),
            ],
            [
                InlineKeyboardButton("📅 Тиждень",          callback_data="help_week"),
                InlineKeyboardButton("🗂 Категорії",        callback_data="help_categories"),
            ],
            [
                InlineKeyboardButton("🔥 Розбір витрат",    callback_data="help_roast"),
                InlineKeyboardButton("💡 Порада",           callback_data="help_advice"),
            ],
            [
                InlineKeyboardButton("🔁 Рекласифікація",   callback_data="help_reclassify"),
                InlineKeyboardButton("💰 Трекер витрат",    callback_data="help_expenses"),
            ],
        ]
        if mono_partner:
            rows.append([
                InlineKeyboardButton(f"👤 Синк {partner_label}", callback_data="help_syncpartner"),
                InlineKeyboardButton("👨‍👩‍ Сімейний",              callback_data="help_family"),
            ])
        rows.append([InlineKeyboardButton("🆔 Мій ID",      callback_data="help_myid")])
        return InlineKeyboardMarkup(rows)

    _HELP_DETAILS = {
        "help_sync":        "🔄 *Синхронізація Monobank*\n\n/sync — останні 30 днів\n/sync 7 — довільна кількість днів\nАбо надішли *.csv / .xlsx* з Privat24 — імпортую автоматично",
        "help_stats":       "📊 *Статистика за місяць*\n\n/stats — загальна картина: витрати, категорії, топ-5\nВключає патерни (нічні витрати, часті категорії)",
        "help_week":        "📅 *Статистика за тиждень*\n\n/week — останні 7 днів у розбивці",
        "help_categories":  "🗂 *Категорії*\n\n/categories — повний розклад по категоріях з відсотками\n/reclassify — повторна класифікація транзакцій у «Інше»",
        "help_roast":       "🔥 *AI-розбір витрат*\n\n/roast — жорсткий розбір польотів з конкретними цифрами",
        "help_advice":      "💡 *AI-порада*\n\n/advice — топ-3 де скоротити, конкретний план на цей тиждень",
        "help_reclassify":  "🔁 *Рекласифікація*\n\n/reclassify — AI повторно класифікує всі транзакції у «❓ Інше»\nТе що AI не впізнає — покаже по одній з повною інфою для ручної класифікації",
        "help_expenses":    "💰 *Трекер витрат*\n\n/expenses — меню трекера\n/estats — статистика витрат (з перемикачем місяць/рік/весь час)\n/history — останні записи\n\nАбо просто напиши витрату:\n_Готель 725 EUR 14.02_\n_Їжа 350_\nБот запитає про пропущені поля 👇",
        "help_myid":        "🆔 *Мій Telegram ID*\n\n/myid — показати свій ID для налаштування бота",
    }

    async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        await update.message.reply_text(
            "💳 *MONOBOT*\nФінансовий трекер без цензури\n\nВибери що потрібно 👇",
            reply_markup=_help_keyboard(),
            parse_mode="Markdown",
        )

    async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        await update.message.reply_text(
            "💳 *MONOBOT* — що вміє бот?\nВибери розділ 👇",
            reply_markup=_help_keyboard(),
            parse_mode="Markdown",
        )

    async def help_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        detail = _HELP_DETAILS.get(query.data)
        if detail:
            back = InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="help_back")]])
            await query.edit_message_text(detail, reply_markup=back, parse_mode="Markdown")

    async def help_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "💳 *MONOBOT* — що вміє бот?\nВибери розділ 👇",
            reply_markup=_help_keyboard(),
            parse_mode="Markdown",
        )

    async def myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"Твій Telegram ID: `{update.effective_user.id}`\n\n"
            f"Додай в Railway Variables:\n`MY_TELEGRAM_ID={update.effective_user.id}`",
            parse_mode="Markdown"
        )

    def _do_sync(mono_client: MonobankClient, owner_str: str, days: int) -> tuple[int, int]:
        accounts = mono_client.get_accounts()
        total_fetched = 0
        total_new = 0
        for account in accounts[:2]:
            if account.get("currencyCode", 980) != 980:
                continue
            account_id = account["id"]
            transactions = mono_client.get_statement(account_id, days=days)
            total_fetched += len(transactions)
            for tx in transactions:
                if db.transaction_exists(tx["id"]):
                    continue
                category = classifier.classify(tx, owner=owner_str) if tx["amount"] < 0 else "💰 Надходження"
                db.save_transaction(tx, category, account_id, owner=owner_str)
                total_new += 1
        return total_fetched, total_new

    async def sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        days = int(ctx.args[0]) if ctx.args else 30
        msg = await update.message.reply_text(f"⏳ Синхронізую {days} днів...")
        try:
            loop = asyncio.get_running_loop()
            fetched, total_new = await loop.run_in_executor(None, lambda: _do_sync(mono, owner, days))
            already = fetched - total_new
            await msg.edit_text(
                f"✅ Синк завершено\n\n"
                f"Отримано від банку: {fetched}\n"
                f"Нових збережено: {total_new}\n"
                f"Вже були в базі: {already}\n\n"
                f"/stats — подивитись\n/roast — почути правду"
            )
        except Exception as e:
            logger.error(f"Sync error: {e}", exc_info=True)
            await msg.edit_text(f"❌ Синк впав:\n{e}")

    async def syncprivat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        await update.message.reply_text(
            "📲 *Як імпортувати Privat24:*\n\n"
            "1. Відкрий Privat24\n"
            "2. Виписка → обери період → Експортувати\n"
            "3. Формат: CSV або XLSX\n"
            "4. Надішли файл сюди\n\n"
            "_Бот сам розпарсить і збереже транзакції_",
            parse_mode="Markdown"
        )

    async def syncpartner(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        if not mono_partner:
            await update.message.reply_text(
                f"Щоб додати {partner_label}, встанови в Railway Variables:\n"
                "PARTNER_MONO_TOKEN=токен_партнера"
            )
            return
        days = int(ctx.args[0]) if ctx.args else 30
        msg = await update.message.reply_text(f"⏳ Синхронізую {partner_label} за {days} днів...")
        try:
            loop = asyncio.get_running_loop()
            _, total_new = await loop.run_in_executor(None, lambda: _do_sync(mono_partner, "partner", days))
            await msg.edit_text(
                f"✅ Готово!\n\nНових транзакцій {partner_label}: {total_new}\n\n/family — переглянути разом"
            )
        except Exception as e:
            await msg.edit_text(f"❌ Помилка: {e}")

    async def reclassify(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        user_id = update.effective_user.id
        msg = await update.message.reply_text("🔄 Перекласифіковую 'Інше' через AI...")
        try:
            with db.conn() as con:
                rows = [dict(r) for r in con.execute(
                    "SELECT * FROM transactions WHERE category = '❓ Інше' AND amount < 0 AND owner = ?",
                    (owner,)
                ).fetchall()]

            if not rows:
                await msg.edit_text("✅ Немає транзакцій для перекласифікації")
                return

            total = len(rows)
            await msg.edit_text(f"🔄 Знайдено {total}, запускаю AI...")
            loop = asyncio.get_running_loop()
            updated = 0
            still_unknown = []

            for i, row in enumerate(rows):
                # Update progress every 10 transactions
                if i > 0 and i % 10 == 0:
                    try:
                        await msg.edit_text(
                            f"🔄 AI класифікує... {i}/{total}\n"
                            f"✅ Вже визначено: {updated}"
                        )
                    except Exception:
                        pass

                try:
                    category = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, lambda r=row: classifier.classify(r, owner=owner, force=True)
                        ),
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    category = "❓ Інше"

                if category != "❓ Інше":
                    with db.conn() as con:
                        con.execute("UPDATE transactions SET category = ? WHERE id = ?",
                                    (category, row["id"]))
                    updated += 1
                else:
                    still_unknown.append(row["id"])

            if not still_unknown:
                await msg.edit_text(
                    f"✅ Готово!\n\nАвто-класифіковано: {updated} з {len(rows)}\n/categories — переглянути"
                )
                return

            _reclassify_queue[user_id] = still_unknown
            await msg.edit_text(
                f"✅ AI впорався з {updated} з {len(rows)}\n"
                f"❓ Залишилось невідомих: {len(still_unknown)}\n\n"
                f"Пройдемося по них разом 👇"
            )
            await _ask_next_reclassify(ctx.bot, update.effective_chat.id, user_id)
        except Exception as e:
            logger.error(f"Reclassify error: {e}", exc_info=True)
            await msg.edit_text(f"❌ Помилка: {e}")

    async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        msg = await update.message.reply_text("📊 Рахую збитки...")
        try:
            text = analytics.monthly_stats(owner=owner)
            patterns = get_pattern_summary(db, owner)
            if patterns:
                text += f"\n\n⚠️ Патерни:\n{patterns}"
            await msg.edit_text(text)
        except Exception as e:
            await msg.edit_text(f"❌ Помилка: {e}")

    async def week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        msg = await update.message.reply_text("📅 Рахую тиждень...")
        try:
            await msg.edit_text(analytics.weekly_stats(owner=owner))
        except Exception as e:
            await msg.edit_text(f"❌ Помилка: {e}")

    async def categories(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        msg = await update.message.reply_text("🗂 Збираю категорії...")
        try:
            await msg.edit_text(analytics.categories_breakdown(owner=owner))
        except Exception as e:
            await msg.edit_text(f"❌ Помилка: {e}")

    async def family(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        msg = await update.message.reply_text("👨‍👩‍ Рахую сімейний бюджет...")
        try:
            await msg.edit_text(analytics.family_stats(partner_label))
        except Exception as e:
            await msg.edit_text(f"❌ Помилка: {e}")

    async def roast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        msg = await update.message.reply_text("🔥 AI вивчає твої гріхи...")
        try:
            patterns = get_pattern_summary(db, owner)
            text = await analytics.roast(owner=owner)
            if patterns:
                text += f"\n\n⚠️ Патерни:\n{patterns}"
            await msg.edit_text(text)
        except Exception as e:
            await msg.edit_text(f"❌ Помилка: {e}")

    async def advice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        msg = await update.message.reply_text("💡 Складаю план порятунку...")
        try:
            await msg.edit_text(await analytics.advice(owner=owner))
        except Exception as e:
            await msg.edit_text(f"❌ Помилка: {e}")

    async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Handle CSV/XLSX file uploads for Privat24 import."""
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return

        doc = update.message.document
        if not doc:
            return

        fname = doc.file_name or ""
        if not (fname.lower().endswith(".csv") or
                fname.lower().endswith(".xlsx") or
                fname.lower().endswith(".xls")):
            return  # not a statement file — ignore

        msg = await update.message.reply_text(f"📂 Обробляю {fname}...")
        try:
            tg_file = await ctx.bot.get_file(doc.file_id)
            file_bytes = await tg_file.download_as_bytearray()
            txs = parse_privat_csv(bytes(file_bytes), fname)

            if not txs:
                await msg.edit_text("❌ Не знайшов транзакцій. Перевір формат файлу.")
                return

            new_count = 0
            for tx in txs:
                if db.transaction_exists(tx["id"]):
                    continue
                category = classifier.classify(tx, owner=owner) if tx["amount"] < 0 else "💰 Надходження"
                db.save_transaction(tx, category, "privat", owner=owner)
                new_count += 1

            await msg.edit_text(
                f"✅ Privat24 імпорт завершено\n\n"
                f"Всього в файлі: {len(txs)}\n"
                f"Нових збережено: {new_count}\n"
                f"Вже були в базі: {len(txs) - new_count}\n\n"
                f"/stats — переглянути"
            )
        except PrivatCSVError as e:
            await msg.edit_text(f"❌ Не вдалось розпарсити файл:\n{e}")
        except Exception as e:
            logger.error(f"Document import error: {e}", exc_info=True)
            await msg.edit_text(f"❌ Помилка: {e}")

    async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return

        user_id = update.effective_user.id

        # Check if this is a classification reply
        if user_id in _pending_classification:
            tx_id = _pending_classification.pop(user_id)
            user_input = update.message.text.strip()

            # Remove from reclassify queue regardless of outcome
            if user_id in _reclassify_queue and tx_id in _reclassify_queue[user_id]:
                _reclassify_queue[user_id].remove(tx_id)

            # Skip command
            if user_input.lower() in ("пропустити", "skip", "п"):
                await update.message.reply_text("⏭ Пропустив")
                if _reclassify_queue.get(user_id):
                    await _ask_next_reclassify(ctx.bot, update.effective_chat.id, user_id)
                return

            # Try to map to a known valid category
            matched = next(
                (c for c in VALID_CATEGORIES if user_input.lower() in c.lower() or c.lower() in user_input.lower()),
                None
            )
            category = matched or user_input  # use raw input if no match — user knows better

            # Save keyword for future auto-classification
            # Try pending_classifications table first, fall back to transactions table
            pending = db.get_pending_classifications(owner)
            pending_tx = next((p for p in pending if p["tx_id"] == tx_id), None)
            if pending_tx:
                source_desc = pending_tx["description"]
                db.resolve_pending_classification(tx_id, category)
            else:
                tx_row = db.get_transaction_by_id(tx_id)
                source_desc = tx_row["description"] if tx_row else ""
                with db.conn() as con:
                    con.execute("UPDATE transactions SET category = ? WHERE id = ?", (category, tx_id))

            if source_desc:
                keyword = source_desc.lower().split()[0]
                if len(keyword) >= 3:
                    db.save_custom_keyword(keyword, category, owner)

            label = matched or user_input
            await update.message.reply_text(f"✅ *{label}*", parse_mode="Markdown")

            if _reclassify_queue.get(user_id):
                await _ask_next_reclassify(ctx.bot, update.effective_chat.id, user_id)
            return

        await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
        try:
            reply = await analytics.chat(user_id, update.message.text, owner=owner)
            await update.message.reply_text(reply)
        except Exception as e:
            await update.message.reply_text(f"❌ Помилка: {e}")

    return {
        "start": start,
        "help": help_cmd,
        "help_callback": help_callback,
        "help_back": help_back,
        "myid": myid,
        "sync": sync,
        "syncprivat": syncprivat,
        "syncpartner": syncpartner,
        "reclassify": reclassify,
        "stats": stats,
        "week": week,
        "categories": categories,
        "family": family,
        "roast": roast,
        "advice": advice,
        "handle_document": handle_document,
        "chat": chat,
        "has_partner": mono_partner is not None,
    }
