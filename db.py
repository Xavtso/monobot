import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager


class Database:
    def __init__(self, path: str = "monobot.db"):
        self.path = path
        self._init_db()

    @contextmanager
    def conn(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _init_db(self):
        with self.conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    account_id TEXT,
                    time INTEGER,
                    description TEXT,
                    mcc INTEGER,
                    amount INTEGER,
                    currency INTEGER,
                    category TEXT,
                    comment TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def transaction_exists(self, tx_id: str) -> bool:
        with self.conn() as con:
            row = con.execute(
                "SELECT 1 FROM transactions WHERE id = ?", (tx_id,)
            ).fetchone()
            return row is not None

    def save_transaction(self, tx: dict, category: str, account_id: str):
        with self.conn() as con:
            con.execute("""
                INSERT OR IGNORE INTO transactions
                (id, account_id, time, description, mcc, amount, currency, category, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx["id"],
                account_id,
                tx.get("time", 0),
                tx.get("description", ""),
                tx.get("mcc", 0),
                tx.get("amount", 0),
                tx.get("currencyCode", 980),
                category,
                tx.get("comment", ""),
            ))

    def get_transactions(self, days: int = 30, only_expenses: bool = True) -> list:
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        query = "SELECT * FROM transactions WHERE time >= ?"
        params = [since]

        if only_expenses:
            query += " AND amount < 0"

        query += " ORDER BY time DESC"

        with self.conn() as con:
            rows = con.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_categories_summary(self, days: int = 30) -> list:
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        with self.conn() as con:
            rows = con.execute("""
                SELECT category, 
                       COUNT(*) as count,
                       SUM(ABS(amount)) as total
                FROM transactions
                WHERE time >= ? AND amount < 0
                GROUP BY category
                ORDER BY total DESC
            """, (since,)).fetchall()
            return [dict(r) for r in rows]

    def get_total_spent(self, days: int = 30) -> int:
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        with self.conn() as con:
            row = con.execute("""
                SELECT SUM(ABS(amount)) as total
                FROM transactions
                WHERE time >= ? AND amount < 0
            """, (since,)).fetchone()
            return row["total"] or 0

    def get_top_merchants(self, days: int = 30, limit: int = 5) -> list:
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        with self.conn() as con:
            rows = con.execute("""
                SELECT description,
                       COUNT(*) as count,
                       SUM(ABS(amount)) as total
                FROM transactions
                WHERE time >= ? AND amount < 0
                GROUP BY description
                ORDER BY total DESC
                LIMIT ?
            """, (since, limit)).fetchall()
            return [dict(r) for r in rows]
