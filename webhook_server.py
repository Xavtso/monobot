import logging
from aiohttp import web
from notifier import format_notification

logger = logging.getLogger(__name__)


async def build_webhook_app(db, classifier, telegram_bot, chat_id: int):

    async def handle(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400)

        if body.get("type") != "StatementItem":
            return web.Response(status=200)

        data = body.get("data", {})
        tx = data.get("statementItem", {})

        if not tx or tx.get("amount", 0) >= 0:
            return web.Response(status=200)

        try:
            tx_id = tx.get("id", "")
            if db.transaction_exists(tx_id):
                return web.Response(status=200)

            account_id = data.get("account", "")
            category = classifier.classify(tx)
            db.save_transaction(tx, category, account_id)

            # Рахуємо місячну статистику по категорії
            cats = db.get_categories_summary(days=30)
            cat_data = next((c for c in cats if c["category"] == category), None)
            monthly_total = cat_data["total"] if cat_data else abs(tx.get("amount", 0))
            monthly_count = cat_data["count"] if cat_data else 1

            text = format_notification(tx, category, monthly_total, monthly_count)
            await telegram_bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Webhook processing error: {e}")

        return web.Response(status=200)

    app = web.Application()
    app.router.add_post("/webhook", handle)
    return app
