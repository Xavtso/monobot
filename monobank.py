import requests
import time
from datetime import datetime, timedelta


class MonobankClient:
    BASE_URL = "https://api.monobank.ua"

    def __init__(self, token: str):
        self.token = token
        self.headers = {"X-Token": token}

    def get_accounts(self) -> list:
        """Отримати список рахунків"""
        resp = requests.get(
            f"{self.BASE_URL}/personal/client-info",
            headers=self.headers
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("accounts", [])

    def get_statement(self, account_id: str, days: int = 30) -> list:
        """Отримати виписку за N днів"""
        to_ts = int(time.time())
        from_ts = int((datetime.now() - timedelta(days=days)).timestamp())

        # Monobank обмежує: max 31 день за один запит
        all_transactions = []
        chunk_days = 30

        current_to = to_ts
        remaining = days

        while remaining > 0:
            chunk = min(chunk_days, remaining)
            current_from = current_to - (chunk * 86400)

            resp = requests.get(
                f"{self.BASE_URL}/personal/statement/{account_id}/{current_from}/{current_to}",
                headers=self.headers
            )

            if resp.status_code == 429:
                time.sleep(65)  # rate limit — 1 запит на хвилину
                continue

            resp.raise_for_status()
            transactions = resp.json()

            if isinstance(transactions, list):
                all_transactions.extend(transactions)

            current_to = current_from
            remaining -= chunk

            if remaining > 0:
                time.sleep(65)  # API rate limit між запитами

        return all_transactions

    def get_client_info(self) -> dict:
        resp = requests.get(
            f"{self.BASE_URL}/personal/client-info",
            headers=self.headers
        )
        resp.raise_for_status()
        return resp.json()

    def set_webhook(self, url: str) -> bool:
        resp = requests.post(
            f"{self.BASE_URL}/personal/webhook",
            headers=self.headers,
            json={"webHookUrl": url}
        )
        return resp.status_code == 200
