import logging
import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

from monobank import MonobankClient
from db import Database
from classifier import Classifier
from analytics import Analytics
from webhook_server import build_webhook_app

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()
mono = MonobankClient(os.getenv("MONO_TOKEN"))
classifier = Classifier(os.getenv("GROQ_API_KEY"))
analytics = Analytics(db, os.getenv("GROQ_API_KEY"))

# Партнерський клієнт — якщо токен заданий
partner_token = os.getenv("PARTNER_MONO_TOKEN")
mono_partner = MonobankClient(partner_token) if partner_token else None
partner_label = os.getenv("PARTNER_LABEL", "партнер")


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    has_partner = mono_partner is not None
    partner_hint = f"\n/syncpartner — синхронізувати {partner_label}\n/family — сімейний бюджет" if has_partner else ""
    await update.message.reply_text(
        "💳 MONOBOT\n"
        "Твій фінансовий радник без цензури\n\n"
        "━━━━━━━━━━━━━━━\n"
        "/sync — злити транзакції з моно\n"
        "/stats — що ти наробив за місяць\n"
        "/week — тижнева картина маслом\n"
        "/categories — повний розклад\n"
        "/reclassify — переосмислити некласифіковані\n"
        "/roast — отримати по щці від AI\n"
        "/advice — план як стати менш бідним"
        f"{partner_hint}\n"
        "━━━━━━━━━━━━━━━\n\n"
        "Або просто напиши що хочеш дізнатись 👇\n"
        "Починай з /sync"
    )


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    has_partner = mono_partner is not None
    partner_section = (
        f"\n👨‍👩‍ Сімейний бюджет\n"
        f"/syncpartner — синхронізувати {partner_label}\n"
        f"/family — витрати разом і окремо"
    ) if has_partner else ""

    await update.message.reply_text(
        "💳 MONOBOT — список команд\n\n"
        "📥 Синхронізація\n"
        "/sync — завантажити транзакції (останні 30 днів)\n"
        "/sync 7 — завантажити за довільну кількість днів\n"
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
        "Просто напиши будь-яке питання — бот відповість з урахуванням твоїх витрат\n\n"
        "⚙️ Інше\n"
        "/myid — дізнатись свій Telegram ID\n"
        "/help — цей список"
    )


async def myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Твій Telegram ID: {update.effective_user.id}\n\n"
        f"Додай в Railway Variables:\nTELEGRAM_CHAT_ID={update.effective_user.id}"
    )


def _do_sync(mono_client: MonobankClient, owner: str, days: int) -> int:
    accounts = mono_client.get_accounts()
    total_new = 0
    for account in accounts[:2]:
        account_id = account["id"]
        if account.get("currencyCode", 980) != 980:
            continue
        transactions = mono_client.get_statement(account_id, days=days)
        for tx in transactions:
            if db.transaction_exists(tx["id"]):
                continue
            category = classifier.classify(tx) if tx["amount"] < 0 else "💰 Надходження"
            db.save_transaction(tx, category, account_id, owner=owner)
            total_new += 1
    return total_new


async def sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    days = int(ctx.args[0]) if ctx.args else 30
    msg = await update.message.reply_text(f"⏳ Синхронізую {days} днів...")
    try:
        loop = asyncio.get_event_loop()
        total_new = await loop.run_in_executor(None, lambda: _do_sync(mono, "me", days))
        await msg.edit_text(
            f"✅ Синк завершено\n\n"
            f"Нових транзакцій: {total_new}\n\n"
            f"/stats — подивитись\n/roast — почути правду"
        )
    except Exception as e:
        logger.error(f"Sync error: {e}")
        await msg.edit_text(f"❌ Синк впав:\n{e}")


async def syncpartner(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not mono_partner:
        await update.message.reply_text(
            f"Щоб додати {partner_label}, встанови в Railway Variables:\n"
            "PARTNER_MONO_TOKEN=токен_партнера\n"
            "PARTNER_LABEL=дівчина  (або як хочеш)"
        )
        return

    days = int(ctx.args[0]) if ctx.args else 30
    msg = await update.message.reply_text(f"⏳ Синхронізую {partner_label} за {days} днів...")
    try:
        loop = asyncio.get_event_loop()
        total_new = await loop.run_in_executor(None, lambda: _do_sync(mono_partner, "partner", days))
        await msg.edit_text(
            f"✅ Готово!\n\nНових транзакцій {partner_label}: {total_new}\n\n/family — переглянути разом"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")


async def reclassify(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Перекласифіковую 'Інше'...")
    try:
        with db.conn() as con:
            rows = con.execute(
                "SELECT id, description, comment, mcc, amount FROM transactions "
                "WHERE category = '❓ Інше' AND amount < 0"
            ).fetchall()

        if not rows:
            await msg.edit_text("✅ Немає транзакцій для перекласифікації")
            return

        await msg.edit_text(f"🔄 Знайдено {len(rows)}, класифікую...")
        updated = 0
        for row in rows:
            tx = {"id": row["id"], "description": row["description"],
                  "comment": row["comment"], "mcc": row["mcc"], "amount": row["amount"]}
            category = classifier.classify(tx)
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
    msg = await update.message.reply_text("📊 Рахую збитки...")
    try:
        await msg.edit_text(analytics.monthly_stats())
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")


async def week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📅 Рахую тиждень...")
    try:
        await msg.edit_text(analytics.weekly_stats())
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")


async def categories(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🗂 Збираю категорії...")
    try:
        await msg.edit_text(analytics.categories_breakdown())
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")


async def family(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("👨‍👩‍ Рахую сімейний бюджет...")
    try:
        await msg.edit_text(analytics.family_stats(partner_label))
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")


async def roast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔥 AI вивчає твої гріхи...")
    try:
        await msg.edit_text(await analytics.roast())
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")


async def advice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("💡 Складаю план порятунку...")
    try:
        await msg.edit_text(await analytics.advice())
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")


async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        reply = await analytics.chat(user_id, update.message.text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")


def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN не встановлено в .env")

    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    has_partner = mono_partner is not None

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("sync", sync))
    app.add_handler(CommandHandler("reclassify", reclassify))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("categories", categories))
    app.add_handler(CommandHandler("roast", roast))
    app.add_handler(CommandHandler("advice", advice))
    if has_partner:
        app.add_handler(CommandHandler("syncpartner", syncpartner))
        app.add_handler(CommandHandler("family", family))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    async def post_init(application):
        commands = [
            ("sync",        "Завантажити транзакції з Monobank"),
            ("stats",       "Статистика за місяць"),
            ("week",        "Статистика за тиждень"),
            ("categories",  "Витрати по категоріях"),
            ("reclassify",  "Переосмислити некласифіковані"),
            ("roast",       "Отримати по щці від AI"),
            ("advice",      "План як стати менш бідним"),
            ("myid",        "Мій Telegram ID"),
            ("help",        "Список всіх команд"),
        ]
        if has_partner:
            commands.insert(2, ("syncpartner", f"Синхронізувати {partner_label}"))
            commands.insert(3, ("family", "Сімейний бюджет"))

        await application.bot.set_my_commands(commands)
        logger.info("Команди синхронізовано ✅")

        port = int(os.getenv("PORT", 8080))
        webhook_app = await build_webhook_app(
            db, classifier, application.bot, int(chat_id) if chat_id else None
        )
        runner = web.AppRunner(webhook_app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
        logger.info(f"Webhook сервер запущено на :{port} ✅")

        webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
        if webhook_url:
            ok = mono.set_webhook(f"{webhook_url}/webhook")
            logger.info(f"Monobank webhook: {'✅' if ok else '❌'} {webhook_url}/webhook")

    app.post_init = post_init

    asyncio.set_event_loop(asyncio.new_event_loop())
    logger.info("Бот запущено 🚀")
    app.run_polling()


if __name__ == "__main__":
    main()
