import os, time, tempfile, pytest
os.environ.setdefault("MY_TELEGRAM_ID", "111")
os.environ.setdefault("PARTNER_TELEGRAM_ID", "222")

from db import Database
from patterns import check_patterns, get_pattern_summary

@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    d = Database(path=path)
    yield d
    os.unlink(path)

def _tx(tx_id, description, amount, ts=None, category="☕ Кафе/Ресторани"):
    return {"id": tx_id, "description": description, "amount": amount,
            "time": ts or int(time.time()), "mcc": 0, "comment": "", "currencyCode": 980}

def test_no_patterns_on_first_transaction(db):
    tx = _tx("t1", "Starbucks", -15000)
    alerts = check_patterns(db, tx, "☕ Кафе/Ресторани", "me")
    assert alerts == []

def test_frequency_pattern_triggers_at_3(db):
    now = int(time.time())
    for i in range(2):
        t = _tx(f"t{i}", "Starbucks", -15000, now - i * 100)
        db.save_transaction(t, "☕ Кафе/Ресторани", "acc", owner="me")

    tx = _tx("t_new", "Starbucks", -15000, now)
    alerts = check_patterns(db, tx, "☕ Кафе/Ресторани", "me")
    assert any("кав" in a.lower() or "раз" in a.lower() or "3" in a for a in alerts)

def test_night_pattern_triggers_between_23_and_5(db):
    import datetime
    # Build a timestamp for 02:30 today
    today = datetime.date.today()
    night_dt = datetime.datetime(today.year, today.month, today.day, 2, 30)
    tx = _tx("t_night", "Bar", -20000, int(night_dt.timestamp()))
    alerts = check_patterns(db, tx, "🍺 Бари", "me")
    assert any("ніч" in a.lower() or "2:" in a or "ранк" in a.lower() for a in alerts)

def test_big_amount_pattern(db):
    now = int(time.time())
    # Save 5 small transactions to establish average ~150₴
    for i in range(5):
        t = _tx(f"t{i}", "Starbucks", -15000, now - i * 86400)
        db.save_transaction(t, "☕ Кафе/Ресторани", "acc", owner="me")
    # Now a big one: 5x average
    tx = _tx("t_big", "Starbucks", -75000, now)
    alerts = check_patterns(db, tx, "☕ Кафе/Ресторани", "me")
    assert any("більш" in a.lower() or "середн" in a.lower() for a in alerts)

def test_get_pattern_summary_returns_string(db):
    result = get_pattern_summary(db, "me")
    assert isinstance(result, str)
