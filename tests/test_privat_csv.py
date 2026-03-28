import pytest
from privat_csv import parse_privat_csv, PrivatCSVError

# Minimal valid Privat24 CSV (semicolon-delimited, UTF-8)
VALID_CSV = (
    "Дата;Час;Категорія;Картка;Отримувач/Відправник;"
    "Сума у валюті картки;Валюта картки;Сума у валюті рахунку;"
    "Валюта рахунку;Залишок на кінець;Валюта залишку\n"
    "01.03.2026;14:30:00;Ресторани;4731****1234;STARBUCKS KYIV;"
    "-150.00;UAH;-150.00;UAH;5000.00;UAH\n"
    "02.03.2026;09:00:00;Інше;4731****1234;SALARY;"
    "5000.00;UAH;5000.00;UAH;10000.00;UAH\n"  # income — should be included
    "03.03.2026;12:00:00;Інше;4731****1234;TRANSFER USD;"
    "-50.00;USD;-2000.00;UAH;4950.00;UAH\n"  # USD — skip
)

def test_parse_returns_list(tmp_path):
    f = tmp_path / "statement.csv"
    f.write_bytes(VALID_CSV.encode("utf-8"))
    txs = parse_privat_csv(f.read_bytes(), "statement.csv")
    assert isinstance(txs, list)

def test_expense_included(tmp_path):
    f = tmp_path / "statement.csv"
    f.write_bytes(VALID_CSV.encode("utf-8"))
    txs = parse_privat_csv(f.read_bytes(), "statement.csv")
    descs = [t["description"] for t in txs]
    assert "STARBUCKS KYIV" in descs

def test_income_included(tmp_path):
    f = tmp_path / "statement.csv"
    f.write_bytes(VALID_CSV.encode("utf-8"))
    txs = parse_privat_csv(f.read_bytes(), "statement.csv")
    descs = [t["description"] for t in txs]
    assert "SALARY" in descs

def test_non_uah_excluded(tmp_path):
    f = tmp_path / "statement.csv"
    f.write_bytes(VALID_CSV.encode("utf-8"))
    txs = parse_privat_csv(f.read_bytes(), "statement.csv")
    descs = [t["description"] for t in txs]
    assert "TRANSFER USD" not in descs

def test_amount_in_kopecks(tmp_path):
    f = tmp_path / "statement.csv"
    f.write_bytes(VALID_CSV.encode("utf-8"))
    txs = parse_privat_csv(f.read_bytes(), "statement.csv")
    starbucks = next(t for t in txs if t["description"] == "STARBUCKS KYIV")
    assert starbucks["amount"] == -15000  # -150.00 UAH → -15000 kopecks

def test_deterministic_id(tmp_path):
    f = tmp_path / "statement.csv"
    f.write_bytes(VALID_CSV.encode("utf-8"))
    txs1 = parse_privat_csv(f.read_bytes(), "statement.csv")
    txs2 = parse_privat_csv(f.read_bytes(), "statement.csv")
    assert txs1[0]["id"] == txs2[0]["id"]

def test_invalid_file_raises(tmp_path):
    f = tmp_path / "garbage.csv"
    f.write_bytes(b"this is not a valid privat csv")
    with pytest.raises(PrivatCSVError):
        parse_privat_csv(f.read_bytes(), "garbage.csv")
