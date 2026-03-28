import os


def get_owner(telegram_id: int) -> str | None:
    """Map Telegram user_id to owner string. Returns None for unknown users."""
    if not telegram_id:
        return None
    my_id = os.getenv("MY_TELEGRAM_ID", "")
    partner_id = os.getenv("PARTNER_TELEGRAM_ID", "")
    if my_id and telegram_id == int(my_id):
        return "me"
    if partner_id and telegram_id == int(partner_id):
        return "partner"
    return None
