import re
from datetime import date

ALIASES = {
    "готел": "Готель", "готель": "Готель", "hotel": "Готель",
    "авіа": "Авіа", "avia": "Авіа", "flight": "Авіа", "авіаквитки": "Авіа",
    "транспорт": "Транспорт", "транс": "Транспорт", "таксі": "Транспорт",
    "taxi": "Транспорт", "uber": "Транспорт",
    "їжа": "Їжа", "food": "Їжа", "ресторан": "Їжа", "кафе": "Їжа", "обід": "Їжа",
    "розваги": "Розваги", "розвага": "Розваги",
    "медицина": "Медицина", "аптека": "Медицина", "лікар": "Медицина",
    "покупки": "Покупки", "шопінг": "Покупки", "shopping": "Покупки", "магазин": "Покупки",
    "зв'язок": "Зв'язок", "зв": "Зв'язок", "телефон": "Зв'язок",
    "бізнес": "Бізнес", "work": "Бізнес",
    "інше": "Інше", "other": "Інше", "misc": "Інше",
}

DEFAULT_CATEGORIES = [
    "Готель", "Авіа", "Транспорт", "Їжа",
    "Розваги", "Медицина", "Покупки", "Зв'язок", "Бізнес", "Інше",
]

CURRENCIES = {"EUR", "USD", "UAH", "GBP", "PLN"}

_DATE_RE = re.compile(r'^(\d{1,2})\.(\d{2})(?:\.(\d{2,4}))?$')
_NUMBER_RE = re.compile(r'^\d+([.,]\d+)?$')


def _parse_date(token: str) -> str | None:
    """Parse DD.MM or DD.MM.YY or DD.MM.YYYY → YYYY-MM-DD."""
    m = _DATE_RE.match(token)
    if not m:
        return None
    day, month, year_str = m.group(1), m.group(2), m.group(3)
    if year_str:
        year = int(year_str)
        if year < 100:
            year += 2000
    else:
        year = date.today().year
    try:
        return date(year, int(month), int(day)).isoformat()
    except ValueError:
        return None


def parse_expense(text: str) -> dict | None:
    """
    Parse a text message into an expense dict.
    Returns: {category, amount, currency, date} or None if not an expense.
    """
    if not text or text.startswith("/"):
        return None

    tokens = text.strip().split()
    if len(tokens) < 2:
        return None

    # Find first numeric token
    amount_idx = None
    for i, token in enumerate(tokens):
        if _NUMBER_RE.match(token.replace(",", ".")):
            amount_idx = i
            break

    if amount_idx is None or amount_idx == 0:
        return None  # no amount, or amount is first token (no category)

    # Category = everything before the amount
    raw_category = " ".join(tokens[:amount_idx]).lower().strip()

    # Resolve via aliases (full phrase, then first word)
    category = ALIASES.get(raw_category)
    if not category:
        category = ALIASES.get(tokens[0].lower())
    if not category:
        # Use raw input capitalized — user may have custom category
        category = " ".join(w.capitalize() for w in tokens[:amount_idx])

    # Parse amount
    try:
        amount = float(tokens[amount_idx].replace(",", "."))
    except ValueError:
        return None
    if amount <= 0:
        return None

    # Parse optional currency and date from remaining tokens
    currency = "UAH"
    expense_date = date.today().isoformat()

    for token in tokens[amount_idx + 1:]:
        if token.upper() in CURRENCIES:
            currency = token.upper()
        else:
            parsed_date = _parse_date(token)
            if parsed_date:
                expense_date = parsed_date

    return {"category": category, "amount": amount, "currency": currency, "date": expense_date}
