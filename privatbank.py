import hashlib
import requests
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta


class PrivatBankClient:
    BASE_URL = "https://api.privatbank.ua/p24api"

    def __init__(self, merchant_id: str, password: str, card: str):
        self.merchant_id = merchant_id
        self.password = password
        self.card = card

    def _sign(self, data_xml: str) -> str:
        raw = data_xml + self.password
        md5 = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return hashlib.sha1(md5.encode("utf-8")).hexdigest()

    def _build_request(self, data_xml: str) -> str:
        sig = self._sign(data_xml)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<request version=\"1.0\">"
            f"<merchant><id>{self.merchant_id}</id><signature>{sig}</signature></merchant>"
            f"<data>{data_xml}</data>"
            "</request>"
        )

    def get_statement(self, days: int = 30) -> list:
        all_transactions = []
        today = datetime.now()

        # PrivatBank повертає max 90 днів за один запит
        chunk = min(days, 90)
        date_from = (today - timedelta(days=chunk)).strftime("%d.%m.%Y")
        date_to = today.strftime("%d.%m.%Y")

        data_xml = (
            "<oper>cmt</oper><wait>0</wait><test>0</test>"
            f'<payment id=""><prop name="sd" value="{date_from}"/>'
            f'<prop name="ed" value="{date_to}"/>'
            f'<prop name="card" value="{self.card}"/></payment>'
        )

        resp = requests.post(
            f"{self.BASE_URL}/statements",
            data=self._build_request(data_xml).encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            timeout=30,
        )
        resp.raise_for_status()

        all_transactions.extend(self._parse_response(resp.text))
        return all_transactions

    def _parse_response(self, xml_text: str) -> list:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        statements = root.find(".//statements")
        if statements is None:
            return []

        result = []
        for stmt in statements.findall("statement"):
            tx = self._normalize(stmt)
            if tx:
                result.append(tx)
        return result

    def _normalize(self, stmt) -> dict:
        """Нормалізує PrivatBank транзакцію до формату Monobank"""
        try:
            # Парсимо дату і час
            trandate = stmt.get("trandate", "")  # "01.01.2024"
            trantime = stmt.get("trantime", "00:00:00")
            dt = datetime.strptime(f"{trandate} {trantime}", "%d.%m.%Y %H:%M:%S")
            ts = int(dt.timestamp())

            # Сума: "-150.00UAH" → -15000 копійок
            amount_str = stmt.get("cardamount", "0UAH").replace("UAH", "").replace(" ", "")
            amount_hrn = float(amount_str)
            amount_kopecks = int(amount_hrn * 100)

            # Баланс: "1000.00UAH" → копійки
            rest_str = stmt.get("rest", "0UAH").replace("UAH", "").replace(" ", "")
            balance_kopecks = int(float(rest_str) * 100)

            description = stmt.get("description", "").strip()
            appcode = stmt.get("appcode", "")

            # Унікальний ID з дати + appcode + суми
            tx_id = f"pb_{ts}_{appcode}_{amount_kopecks}"

            return {
                "id": tx_id,
                "time": ts,
                "description": description,
                "mcc": 0,
                "amount": amount_kopecks,
                "currencyCode": 980,
                "balance": balance_kopecks,
                "comment": stmt.get("terminal", ""),
            }
        except Exception:
            return None

    def get_client_info(self) -> dict:
        return {"card": self.card, "merchant_id": self.merchant_id}
