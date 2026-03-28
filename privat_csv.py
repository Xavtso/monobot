import csv
import hashlib
import io
from datetime import datetime


class PrivatCSVError(Exception):
    pass


# Expected column header substrings (case-insensitive, partial match)
_COL_DATE = "дата"
_COL_TIME = "час"
_COL_DESC = "отримувач"
_COL_AMOUNT = "сума у валюті картки"
_COL_CURRENCY = "валюта картки"
_COL_BALANCE = "залишок"


def parse_privat_csv(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Parse Privat24 statement export (CSV or XLSX) into Monobank-compatible transaction dicts.

    Returns list of dicts with keys: id, time, description, mcc, amount, currencyCode,
    balance, comment.

    Raises PrivatCSVError on unrecognized format.
    """
    name_lower = filename.lower()
    if name_lower.endswith(".xlsx") or name_lower.endswith(".xls"):
        return _parse_xlsx(file_bytes)
    return _parse_csv_bytes(file_bytes)


def _parse_csv_bytes(file_bytes: bytes) -> list[dict]:
    # Try UTF-8 first, fallback to cp1251
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise PrivatCSVError("Cannot decode file — try saving as UTF-8 CSV")

    # Detect delimiter
    first_line = text.split("\n")[0]
    delimiter = ";" if ";" in first_line else ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = reader.fieldnames
    if not headers:
        raise PrivatCSVError("No headers found in CSV")

    col_map = _map_columns(headers)
    return _read_rows(reader, col_map)


def _parse_xlsx(file_bytes: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        raise PrivatCSVError("openpyxl not installed — pip install openpyxl")

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise PrivatCSVError("Empty XLSX file")

    headers = [str(h).strip() if h else "" for h in rows[0]]
    col_map = _map_columns(headers)

    results = []
    for row in rows[1:]:
        row_dict = {headers[i]: (str(row[i]).strip() if row[i] is not None else "")
                    for i in range(len(headers))}
        tx = _parse_row(row_dict, col_map)
        if tx:
            results.append(tx)
    return results


def _map_columns(headers: list[str]) -> dict:
    lower = [h.lower() for h in headers]
    result = {}
    mappings = {
        "date": _COL_DATE,
        "time": _COL_TIME,
        "desc": _COL_DESC,
        "amount": _COL_AMOUNT,
        "currency": _COL_CURRENCY,
        "balance": _COL_BALANCE,
    }
    for key, substr in mappings.items():
        matches = [h for h in lower if substr in h]
        if matches:
            result[key] = headers[lower.index(matches[0])]

    if "date" not in result or "amount" not in result:
        raise PrivatCSVError(
            f"Unrecognized CSV format. Expected columns with: '{_COL_DATE}', '{_COL_AMOUNT}'. "
            f"Got: {headers}"
        )
    return result


def _read_rows(reader, col_map: dict) -> list[dict]:
    results = []
    for row in reader:
        tx = _parse_row(row, col_map)
        if tx:
            results.append(tx)
    return results


def _parse_row(row: dict, col_map: dict) -> dict | None:
    try:
        date_str = row.get(col_map["date"], "").strip()
        time_str = row.get(col_map.get("time", ""), "00:00:00").strip() or "00:00:00"
        description = row.get(col_map.get("desc", ""), "").strip()
        amount_str = row.get(col_map["amount"], "0").strip().replace(",", ".").replace(" ", "")
        currency = row.get(col_map.get("currency", ""), "UAH").strip().upper()
        balance_str = row.get(col_map.get("balance", ""), "0").strip().replace(",", ".").replace(" ", "")

        if not date_str or not amount_str:
            return None

        # Skip non-UAH transactions
        if currency and currency != "UAH":
            return None

        dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
        ts = int(dt.timestamp())

        amount_hrn = float(amount_str)
        amount_kopecks = int(round(amount_hrn * 100))

        balance_hrn = float(balance_str) if balance_str else 0
        balance_kopecks = int(round(balance_hrn * 100))

        # Deterministic ID from date + amount + description hash
        desc_hash = hashlib.md5(f"{description}{amount_kopecks}".encode()).hexdigest()[:8]
        tx_id = f"pb_{ts}_{desc_hash}"

        return {
            "id": tx_id,
            "time": ts,
            "description": description,
            "mcc": 0,
            "amount": amount_kopecks,
            "currencyCode": 980,
            "balance": balance_kopecks,
            "comment": "",
        }
    except (ValueError, KeyError):
        return None
