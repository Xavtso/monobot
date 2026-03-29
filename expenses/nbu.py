import logging
import aiohttp

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, str]] = {}


async def get_nbu_rate(currency: str, date_str: str) -> tuple[float, str]:
    """
    Returns (rate_uah, source_label) for the given currency on date_str (YYYY-MM-DD).
    Returns (1.0, "—") for UAH.
    Raises ValueError with a user-friendly message on failure.
    """
    currency = currency.upper()
    if currency == "UAH":
        return 1.0, "—"

    cache_key = f"{currency}_{date_str}"
    if cache_key in _cache:
        return _cache[cache_key]

    date_api = date_str.replace("-", "")  # YYYYMMDD
    url = (
        f"https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
        f"?valcode={currency}&date={date_api}&json"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json(content_type=None)

        if not data:
            raise ValueError(f"НБУ не має курсу для {currency} на {date_str}")

        rate = float(data[0]["rate"])
        parts = date_str.split("-")
        display_date = f"{parts[2]}.{parts[1]}.{parts[0]}"
        source = f"НБУ · {display_date}"
        _cache[cache_key] = (rate, source)
        return rate, source

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"NBU API error for {currency} {date_str}: {e}")
        raise ValueError(f"Не вдалось отримати курс НБУ для {currency}. Спробуй пізніше.")
