import asyncio
import logging

from telegram import Update
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


def set_pending(user_id: int, tx_id: str):
    """Register a pending classification reply for a user. Called by webhook."""
    _pending_classification[user_id] = tx_id


def setup(db: Database, mono: MonobankClient, classifier: Classifier,
          analytics: Analytics, mono_partner=None, partner_label: str = "партнер"):
    """Return a dict of handler coroutines bound to the given services."""

    async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        privat_hint = "\nНадішли CSV-виписку Privat24 — імпортую автоматично"
        partner_hint = f"\n/syncpartner — синхронізувати {partner_label}\n/family — сімейний бюджет" if mono_partner else ""
        await update.message.reply_text(
            "💳 MONOBOT\n"
            "Фінансовий трекер без цензури\n\n"
            "━━━━━━━━━━━━━━━\n"
            "/sync — злити транзакції з Mono\n"
            f"{privat_hint}"
            "\n/stats — що ти наробив за місяць\n"
            "/week — тижнева картина маслом\n"
            "/categories — повний розклад\n"
            "/reclassify — переосмислити некласифіковані\n"
            "/roast — отримати по щці від AI\n"
            "/advice — план як стати менш бідним"
            f"{partner_hint}\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Або просто напиши що хочеш дізнатись 👇"
        )

    async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        owner = get_owner(update.effective_user.id)
        if owner is None:
            return
        partner_section = (
            f"\n👨‍👩‍ Сімейний бюджет\n"
            f"/syncpartner — синхронізувати {partner_label}\n"
            f"/family — витрати разом і окремо"
        ) if mono_partner else ""

        await update.message.reply_text(
            "💳 MONOBOT — список команд\n\n"
            "📥 Синхронізація\n"
            "/sync — Monobank (останні 30 днів)\n"
            "/sync 7 — за довільну кількість днів\n"
            "Надішли .csv/.xlsx з Privat24 — імпортую\n"
            "/reclassify — переосмислити некласифіковані\n\n"
            "📊 Статистика\n"
            "/stats — місяць у цифрах\n"
            "/week — тиждень\n"
            "/categories — повний розклад по категоріях"
            f"{partner_section}\n\n"
            "🤖 AI-аналіз\n"
            "/roast — жорсткий розбір витрат\n"
            "/advice — конкретний план економії\n\n"
            "💬 Чат\n"
            "Просто напиши будь-яке питання\n\n"
            "⚙️ Інше\n"
            "/myid — дізнатись свій Telegram ID\n"
            "/help — цей список"
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
        msg = await update.message.reply_text("🔄 Перекласифіковую 'Інше'...")
        try:
            with db.conn() as con:
                rows = con.execute(
                    "SELECT id, description, comment, mcc, amount FROM transactions "
                    "WHERE category = '❓ Інше' AND amount < 0 AND owner = ?",
                    (owner,)
                ).fetchall()

            if not rows:
                await msg.edit_text("✅ Немає транзакцій для перекласифікації")
                return

            await msg.edit_text(f"🔄 Знайдено {len(rows)}, класифікую...")
            updated = 0
            for row in rows:
                tx = {"id": row["id"], "description": row["description"],
                      "comment": row["comment"], "mcc": row["mcc"], "amount": row["amount"]}
                category = classifier.classify(tx, owner=owner)
                if category != "❓ Інше":
                    with db.conn() as con:
                        con.execute("UPDATE transactions SET category = ? WHERE id = ?",
                                    (category, row["id"]))
                    updated += 1

            await msg.edit_text(
                f"✅ Готово!\n\nПерекласифіковано: {updated} з {len(rows)}\n/categories — переглянути"
            )
        except Exception as e:
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

            # Try to map to a known category
            matched = next(
                (c for c in VALID_CATEGORIES if user_input.lower() in c.lower() or c.lower() in user_input.lower()),
                None
            )
            category = matched or "❓ Інше"

            # Extract keyword from original description for future classification
            pending = db.get_pending_classifications(owner)
            pending_tx = next((p for p in pending if p["tx_id"] == tx_id), None)
            if pending_tx:
                desc = pending_tx["description"].lower().split()[0]  # first word as keyword
                if len(desc) >= 3:
                    db.save_custom_keyword(desc, category, owner)

            db.resolve_pending_classification(tx_id, category)

            label = matched or user_input
            await update.message.reply_text(
                f"✅ Записав: *{label}*\n_Наступного разу визначу автоматично_",
                parse_mode="Markdown"
            )
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
