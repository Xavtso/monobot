import os, tempfile, pytest
os.environ.setdefault("MY_TELEGRAM_ID", "111")
os.environ.setdefault("PARTNER_TELEGRAM_ID", "222")

from db import Database

@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    d = Database(path=path)
    yield d
    os.unlink(path)

def test_save_pending_classification(db):
    db.save_pending_classification("tx123", "me", "Starbucks", -15000)
    pending = db.get_pending_classifications("me")
    assert len(pending) == 1
    assert pending[0]["tx_id"] == "tx123"
    assert pending[0]["description"] == "Starbucks"

def test_resolve_pending_classification(db):
    db.save_transaction(
        {"id": "tx123", "time": 0, "description": "Starbucks", "mcc": 0,
         "amount": -15000, "currencyCode": 980, "comment": ""},
        "❓ Інше", "acc1", owner="me"
    )
    db.save_pending_classification("tx123", "me", "Starbucks", -15000)
    db.resolve_pending_classification("tx123", "☕ Кафе/Ресторани")
    pending = db.get_pending_classifications("me")
    assert len(pending) == 0
    # category updated in transactions table
    with db.conn() as con:
        row = con.execute("SELECT category FROM transactions WHERE id=?", ("tx123",)).fetchone()
    assert row["category"] == "☕ Кафе/Ресторани"

def test_save_and_get_custom_keyword(db):
    db.save_custom_keyword("starbucks", "☕ Кафе/Ресторани", "me")
    kws = db.get_custom_keywords("me")
    assert ("starbucks", "☕ Кафе/Ресторани") in kws

def test_custom_keyword_deduplicates(db):
    db.save_custom_keyword("starbucks", "☕ Кафе/Ресторани", "me")
    db.save_custom_keyword("starbucks", "🍔 Фастфуд", "me")  # overwrite
    kws = db.get_custom_keywords("me")
    cats = [cat for kw, cat in kws if kw == "starbucks"]
    assert len(cats) == 1
