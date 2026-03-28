import logging
import os
import asyncio
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv

from monobank import MonobankClient
from db import Database
from classifier import Classifier
from analytics import Analytics
from webhook_server import build_webhook_app, set_mono_public_key
from handlers import setup, set_pending

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()
mono = MonobankClient(os.getenv("MONO_TOKEN"))
classifier = Classifier(os.getenv("GROQ_API_KEY"), db=db)
analytics = Analytics(db, os.getenv("GROQ_API_KEY"))

partner_token = os.getenv("PARTNER_MONO_TOKEN")
mono_partner = MonobankClient(partner_token) if partner_token else None
partner_label = os.getenv("PARTNER_LABEL", "партнер")

handlers = setup(db, mono, classifier, analytics, mono_partner, partner_label)


def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN не встановлено в .env")

    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    has_partner = handlers["has_partner"]

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start",       handlers["start"]))
    app.add_handler(CommandHandler("help",        handlers["help"]))
    app.add_handler(CommandHandler("myid",        handlers["myid"]))
    app.add_handler(CommandHandler("sync",        handlers["sync"]))
    app.add_handler(CommandHandler("syncprivat",  handlers["syncprivat"]))
    app.add_handler(CommandHandler("reclassify",  handlers["reclassify"]))
    app.add_handler(CommandHandler("stats",       handlers["stats"]))
    app.add_handler(CommandHandler("week",        handlers["week"]))
    app.add_handler(CommandHandler("categories",  handlers["categories"]))
    app.add_handler(CommandHandler("roast",       handlers["roast"]))
    app.add_handler(CommandHandler("advice",      handlers["advice"]))
    if has_partner:
        app.add_handler(CommandHandler("syncpartner", handlers["syncpartner"]))
        app.add_handler(CommandHandler("family",      handlers["family"]))

    app.add_handler(MessageHandler(filters.Document.ALL, handlers["handle_document"]))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers["chat"]))

    async def post_init(application):
        commands = [
            ("sync",        "Синхронізувати Monobank"),
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
            commands.insert(1, ("syncpartner", f"Синхронізувати {partner_label}"))
            commands.insert(2, ("family", "Сімейний бюджет"))

        await application.bot.set_my_commands(commands)
        logger.info("Команди синхронізовано ✅")

        port = int(os.getenv("PORT", 8080))
        mono_chat_id = int(chat_id) if chat_id else None

        partner_chat_id_env = os.getenv("PARTNER_TELEGRAM_ID")
        partner_chat_id = int(partner_chat_id_env) if partner_chat_id_env and mono_partner else None

        # Load Monobank public key for webhook verification
        mono_pub_key = os.getenv("MONO_PUBLIC_KEY", "")
        if mono_pub_key:
            set_mono_public_key(mono_pub_key)
            logger.info("Monobank webhook signature verification enabled ✅")
        else:
            logger.warning("MONO_PUBLIC_KEY not set — webhook signature verification disabled ⚠️")

        webhook_app = await build_webhook_app(
            db, classifier, application.bot,
            chat_id_me=mono_chat_id,
            chat_id_partner=partner_chat_id,
        )

        # Wire set_pending and user IDs so webhook can trigger classification replies
        webhook_app["set_pending"] = set_pending
        my_user_id = os.getenv("MY_TELEGRAM_ID")
        if my_user_id:
            webhook_app["user_id_me"] = int(my_user_id)
        if partner_chat_id_env:
            webhook_app["user_id_partner"] = int(partner_chat_id_env)

        runner = web.AppRunner(webhook_app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
        logger.info(f"Webhook сервер запущено на :{port} ✅")

        webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
        if webhook_url:
            ok = mono.set_webhook(f"{webhook_url}/webhook")
            logger.info(f"Monobank webhook (me): {'✅' if ok else '❌'} {webhook_url}/webhook")
            if mono_partner:
                ok_p = mono_partner.set_webhook(f"{webhook_url}/webhook/partner")
                logger.info(f"Monobank webhook (partner): {'✅' if ok_p else '❌'} {webhook_url}/webhook/partner")

    app.post_init = post_init

    asyncio.set_event_loop(asyncio.new_event_loop())
    logger.info("Бот запущено 🚀")
    app.run_polling()


if __name__ == "__main__":
    main()
