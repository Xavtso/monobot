import os


def get_owner(telegram_id: int) -> str | None:
    """Map Telegram user_id to owner string. Returns None for unknown users."""
    if not telegram_id:
        return None
    try:
        my_id_str = os.getenv("MY_TELEGRAM_ID", "")
        partner_id_str = os.getenv("PARTNER_TELEGRAM_ID", "")
        if my_id_str and telegram_id == int(my_id_str):
            return "me"
        if partner_id_str and telegram_id == int(partner_id_str):
            return "partner"
    except ValueError:
        pass
    return None
