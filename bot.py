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


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 MONOBOT\n"
        "Твій фінансовий радник без цензури\n\n"
        "━━━━━━━━━━━━━━━\n"
        "/sync — злити транзакції з моно\n"
        "/stats — що ти наробив за місяць\n"
        "/week — тижнева картина маслом\n"
        "/categories — повний розклад\n"
        "/reclassify — переосмислити 'Інше'\n"
        "/roast — отримати по щці від AI\n"
        "/advice — план як стати менш бідним\n"
        "/setwebhook <url> — live сповіщення про трати\n"
        "/myid — дізнатись свій Telegram ID\n"
        "━━━━━━━━━━━━━━━\n\n"
        "Або просто напиши що хочеш дізнатись 👇\n"
        "Починай з /sync"
    )


async def myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Твій Telegram ID: {update.effective_user.id}\n\n"
        f"Додай в .env:\nTELEGRAM_CHAT_ID={update.effective_user.id}"
    )


async def setwebhook(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "Використання: /setwebhook https://твій-домен.ngrok.io\n\n"
            "Бот підніме сервер на порту 8080, Monobank слатиме події на /webhook\n\n"
            "Для локального тесту:\n"
            "1. brew install ngrok\n"
            "2. ngrok http 8080\n"
            "3. /setwebhook https://xxxx.ngrok.io"
        )
        return

    base_url = ctx.args[0].rstrip("/")
    webhook_url = f"{base_url}/webhook"

    msg = await update.message.reply_text(f"⏳ Реєструю вебхук...")
    ok = mono.set_webhook(webhook_url)

    if ok:
        await msg.edit_text(
            f"✅ Вебхук зареєстровано\n\n"
            f"URL: {webhook_url}\n\n"
            f"Тепер при кожній транзакції отримуватимеш сповіщення миттєво."
        )
    else:
        await msg.edit_text("❌ Monobank відхилив URL. Перевір що адреса публічна і доступна.")


async def sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    days = 30
    if ctx.args:
        try:
            days = int(ctx.args[0])
        except ValueError:
            pass

    msg = await update.message.reply_text(f"⏳ Синхронізую {days} днів з Monobank...")

    try:
        accounts = mono.get_accounts()
        total_new = 0

        for account in accounts[:2]:
            account_id = account["id"]
            if account.get("currencyCode", 980) != 980:
                continue

            transactions = mono.get_statement(account_id, days=days)

            for tx in transactions:
                if db.transaction_exists(tx["id"]):
                    continue

                category = classifier.classify(tx) if tx["amount"] < 0 else "💰 Надходження"
                db.save_transaction(tx, category, account_id)
                total_new += 1

        await msg.edit_text(
            f"✅ Синк завершено\n\n"
            f"Нових транзакцій: {total_new}\n\n"
            f"/stats — подивитись картину\n"
            f"/roast — почути правду в очі"
        )

    except Exception as e:
        logger.error(f"Sync error: {e}")
        await msg.edit_text(f"❌ Синк впав:\n{e}\n\nПеревір MONO_TOKEN в .env")


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

        await msg.edit_text(f"🔄 Знайдено {len(rows)} транзакцій, класифікую...")
        updated = 0

        for row in rows:
            tx = {
                "id": row["id"],
                "description": row["description"],
                "comment": row["comment"],
                "mcc": row["mcc"],
                "amount": row["amount"],
            }
            category = classifier.classify(tx)
            if category != "❓ Інше":
                with db.conn() as con:
                    con.execute(
                        "UPDATE transactions SET category = ? WHERE id = ?",
                        (category, row["id"])
                    )
                updated += 1

        await msg.edit_text(
            f"✅ Готово!\n\n"
            f"Перекласифіковано: {updated} з {len(rows)}\n"
            f"/categories — переглянути результат"
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
    text = update.message.text

    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        reply = await analytics.chat(user_id, text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")


def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN не встановлено в .env")

    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("setwebhook", setwebhook))
    app.add_handler(CommandHandler("sync", sync))
    app.add_handler(CommandHandler("reclassify", reclassify))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("categories", categories))
    app.add_handler(CommandHandler("roast", roast))
    app.add_handler(CommandHandler("advice", advice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    async def post_init(application):
        await application.bot.set_my_commands([
            ("sync",        "Завантажити транзакції з Monobank"),
            ("stats",       "Статистика за місяць"),
            ("week",        "Статистика за тиждень"),
            ("categories",  "Витрати по категоріях"),
            ("reclassify",  "Переосмислити некласифіковані"),
            ("roast",       "Отримати по щці від AI"),
            ("advice",      "План як стати менш бідним"),
            ("setwebhook",  "Підключити live сповіщення"),
            ("myid",        "Мій Telegram ID"),
        ])
        logger.info("Команди синхронізовано ✅")

        # Запускаємо webhook сервер якщо є TELEGRAM_CHAT_ID
        if chat_id:
            webhook_app = await build_webhook_app(
                db, classifier, application.bot, int(chat_id)
            )
            runner = web.AppRunner(webhook_app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", 8080)
            await site.start()
            logger.info("Webhook сервер запущено на :8080 ✅")
        else:
            logger.info("TELEGRAM_CHAT_ID не задано — webhook сервер вимкнено. Запусти /myid")

    app.post_init = post_init

    asyncio.set_event_loop(asyncio.new_event_loop())
    logger.info("Бот запущено 🚀")
    app.run_polling()


if __name__ == "__main__":
    main()
