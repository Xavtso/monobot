import time
import datetime
from db import Database


def check_patterns(db: Database, tx: dict, category: str, owner: str) -> list[str]:
    """
    Check incoming transaction against known spending patterns.
    Returns list of alert strings (empty if no patterns triggered).
    """
    alerts = []
    now_ts = tx.get("time", int(time.time()))
    amount = abs(tx.get("amount", 0))

    # 1. Night spending (23:00–05:00)
    hour = datetime.datetime.fromtimestamp(now_ts).hour
    if hour >= 23 or hour < 5:
        time_str = datetime.datetime.fromtimestamp(now_ts).strftime("%H:%M")
        alerts.append(f"{time_str} ночі. ти взагалі спиш?")

    # 2. Frequency — count same category today
    day_start = int(datetime.datetime.combine(
        datetime.date.today(), datetime.time.min
    ).timestamp())
    with db.conn() as con:
        count_today = con.execute(
            "SELECT COUNT(*) as n FROM transactions "
            "WHERE owner=? AND category=? AND time>=? AND amount<0",
            (owner, category, day_start)
        ).fetchone()["n"]

    if count_today >= 2:  # this tx makes it count_today+1
        total = count_today + 1
        cat_word = _category_word(category)
        alerts.append(f"{total} {cat_word} за день. норм?")

    # 3. Big amount — compare to 30-day average for this category
    with db.conn() as con:
        row = con.execute(
            "SELECT AVG(ABS(amount)) as avg_amt, COUNT(*) as n FROM transactions "
            "WHERE owner=? AND category=? AND amount<0 "
            "AND time >= ?",
            (owner, category, int(time.time()) - 30 * 86400)
        ).fetchone()

    avg = row["avg_amt"] or 0
    count_hist = row["n"] or 0
    if count_hist >= 3 and avg > 0 and amount > avg * 2.5:
        x = round(amount / avg, 1)
        alerts.append(f"в {x}× більше ніж зазвичай тут ({int(avg/100)}₴ середнє)")

    return alerts


def get_pattern_summary(db: Database, owner: str) -> str:
    """
    Scan last 30 days for pattern insights. Returns multi-line string.
    Used in /roast and /stats context.
    """
    lines = []
    now = int(time.time())
    since = now - 30 * 86400

    with db.conn() as con:
        # Most frequent category per day
        rows = con.execute(
            """
            SELECT category,
                   COUNT(*) as total_txs,
                   COUNT(DISTINCT date(time, 'unixepoch', 'localtime')) as days_active,
                   ROUND(CAST(COUNT(*) AS REAL) /
                         NULLIF(COUNT(DISTINCT date(time,'unixepoch','localtime')),0), 1) as per_day
            FROM transactions
            WHERE owner=? AND amount<0 AND time>=?
            GROUP BY category
            HAVING per_day >= 2.0
            ORDER BY per_day DESC
            LIMIT 3
            """,
            (owner, since)
        ).fetchall()

    for r in rows:
        lines.append(
            f"· {r['category']}: {r['per_day']} рази/день ({r['days_active']} днів)"
        )

    with db.conn() as con:
        night_count = con.execute(
            "SELECT COUNT(*) as n FROM transactions "
            "WHERE owner=? AND amount<0 AND time>=? "
            "AND (CAST(strftime('%H', time, 'unixepoch', 'localtime') AS INTEGER) >= 23 "
            "  OR CAST(strftime('%H', time, 'unixepoch', 'localtime') AS INTEGER) < 5)",
            (owner, since)
        ).fetchone()["n"]

    if night_count > 0:
        lines.append(f"· {night_count} нічних транзакцій за місяць")

    return "\n".join(lines) if lines else ""


def _category_word(category: str) -> str:
    mapping = {
        "☕ Кафе/Ресторани": "кав/кафе",
        "🍔 Фастфуд": "фастфуди",
        "🍺 Бари": "бари",
        "🚕 Таксі": "таксі",
        "🛒 Супермаркет": "супермаркети",
        "💡 Підписки": "підписки",
        "⛽ АЗС": "АЗС",
    }
    return mapping.get(category, "транзакції")
