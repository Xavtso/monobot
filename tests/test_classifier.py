import os, tempfile, pytest
os.environ.setdefault("GROQ_API_KEY", "test")
os.environ.setdefault("MY_TELEGRAM_ID", "111")
os.environ.setdefault("PARTNER_TELEGRAM_ID", "222")

from db import Database
from classifier import Classifier

@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    d = Database(path=path)
    yield d
    os.unlink(path)

@pytest.fixture
def clf(db):
    return Classifier(os.getenv("GROQ_API_KEY"), db=db)

def test_custom_keyword_takes_priority(clf, db):
    db.save_custom_keyword("mypizzaplace", "🍔 Фастфуд", "me")
    tx = {"id": "t1", "description": "mypizzaplace", "comment": "", "mcc": 0, "amount": -10000}
    result = clf.classify(tx, owner="me")
    assert result == "🍔 Фастфуд"

def test_mcc_still_works(clf):
    tx = {"id": "t1", "description": "Some shop", "comment": "", "mcc": 5812, "amount": -10000}
    result = clf.classify(tx, owner="me")
    assert result == "☕ Кафе/Ресторани"

def test_builtin_keyword_works(clf):
    tx = {"id": "t1", "description": "Netflix subscription", "comment": "", "mcc": 0, "amount": -20000}
    result = clf.classify(tx, owner="me")
    assert result == "💡 Підписки"
