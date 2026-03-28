from notifier import format_notification

def _tx(amount=-15000, description="Starbucks", ts=1700000000):
    return {"id": "t1", "amount": amount, "balance": 500000,
            "description": description, "time": ts, "comment": ""}

def test_format_includes_amount(capfd):
    text = format_notification(_tx(), "☕ Кафе/Ресторани", 210000, 14, [])
    assert "150" in text

def test_format_includes_category(capfd):
    text = format_notification(_tx(), "☕ Кафе/Ресторани", 210000, 14, [])
    assert "Кафе" in text

def test_format_includes_pattern_alert():
    text = format_notification(_tx(), "☕ Кафе/Ресторани", 210000, 14, ["4 кави за день. норм?"])
    assert "4 кави" in text

def test_format_no_pattern_alert_when_empty():
    text = format_notification(_tx(), "☕ Кафе/Ресторани", 210000, 14, [])
    assert "норм?" not in text
