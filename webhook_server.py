import base64
import json
import logging
from aiohttp import web
from notifier import format_notification
from patterns import check_patterns

logger = logging.getLogger(__name__)

_mono_public_key: bytes | None = None


def set_mono_public_key(b64_key: str):
    global _mono_public_key
    try:
        _mono_public_key = base64.b64decode(b64_key)
    except Exception:
        logger.warning("Could not decode MONO_PUBLIC_KEY — webhook signature verification disabled")


def _verify_signature(body: bytes, x_sign_b64: str) -> bool:
    if not _mono_public_key:
        return True  # verification disabled — log warning already shown at startup
    try:
        from nacl.signing import VerifyKey
        vk = VerifyKey(_mono_public_key)
        sig = base64.b64decode(x_sign_b64)
        vk.verify(body, sig)
        return True
    except Exception:
        return False


async def build_webhook_app(db, classifier, telegram_bot, chat_id, owner: str = "me"):

    async def handle(request: web.Request) -> web.Response:
        body = await request.read()

        x_sign = request.headers.get("X-Sign", "")
        if _mono_public_key:
            if not x_sign or not _verify_signature(body, x_sign):
                logger.warning("Webhook signature missing or invalid — rejected")
                return web.Response(status=400)
        elif x_sign and not _verify_signature(body, x_sign):
            logger.warning("Webhook signature verification failed — rejected")
            return web.Response(status=400)

        try:
            body_json = json.loads(body)
        except Exception:
            return web.Response(status=400)

        if body_json.get("type") != "StatementItem":
            return web.Response(status=200)

        data = body_json.get("data", {})
        tx = data.get("statementItem", {})

        if not tx or tx.get("amount", 0) >= 0:
            return web.Response(status=200)

        try:
            tx_id = tx.get("id", "")
            if db.transaction_exists(tx_id):
                return web.Response(status=200)

            category = classifier.classify(tx, owner=owner)
            account_id = data.get("account", "")
            db.save_transaction(tx, category, account_id, owner=owner)

            cats = db.get_categories_summary(days=30, owner=owner)
            cat_data = next((c for c in cats if c["category"] == category), None)
            monthly_total = cat_data["total"] if cat_data else abs(tx.get("amount", 0))
            monthly_count = cat_data["count"] if cat_data else 1

            pattern_alerts = check_patterns(db, tx, category, owner)

            if chat_id:
                text = format_notification(tx, category, monthly_total, monthly_count, pattern_alerts)
                await telegram_bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

                # Ask for classification if unclassified
                if category == "❓ Інше":
                    amount_hrn = abs(tx.get("amount", 0)) / 100
                    db.save_pending_classification(tx_id, owner, tx.get("description", ""), tx.get("amount", 0))
                    await telegram_bot.send_message(
                        chat_id=chat_id,
                        text=f"❓ Шо це таке — *{tx.get('description', '???')}* {amount_hrn:.0f}₴?\nНапиши категорію або опиши одним словом.",
                        parse_mode="Markdown"
                    )
            else:
                logger.warning(f"Транзакція отримана але TELEGRAM_CHAT_ID не задано: {tx_id}")

        except Exception as e:
            logger.error(f"Webhook processing error: {e}", exc_info=True)

        return web.Response(status=200)

    app = web.Application()
    app.router.add_post("/webhook", handle)
    return app
