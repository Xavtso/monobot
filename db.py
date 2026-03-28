import os
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager


class Database:
    def __init__(self, path: str = None):
        if path is None:
            data_dir = os.getenv("DATA_DIR", ".")
            path = os.path.join(data_dir, "monobot.db")
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
                    owner TEXT DEFAULT 'me',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Міграція — додаємо owner якщо ще нема
            try:
                con.execute("ALTER TABLE transactions ADD COLUMN owner TEXT DEFAULT 'me'")
            except Exception:
                pass
            con.execute("""
                CREATE TABLE IF NOT EXISTS pending_classifications (
                    tx_id TEXT PRIMARY KEY,
                    owner TEXT,
                    description TEXT,
                    amount INTEGER,
                    asked_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS custom_keywords (
                    keyword TEXT,
                    category TEXT,
                    added_by TEXT,
                    PRIMARY KEY (keyword, added_by)
                )
            """)

    def transaction_exists(self, tx_id: str) -> bool:
        with self.conn() as con:
            row = con.execute(
                "SELECT 1 FROM transactions WHERE id = ?", (tx_id,)
            ).fetchone()
            return row is not None

    def save_transaction(self, tx: dict, category: str, account_id: str, owner: str = "me"):
        with self.conn() as con:
            con.execute("""
                INSERT OR IGNORE INTO transactions
                (id, account_id, time, description, mcc, amount, currency, category, comment, owner)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx["id"], account_id,
                tx.get("time", 0), tx.get("description", ""),
                tx.get("mcc", 0), tx.get("amount", 0),
                tx.get("currencyCode", 980), category,
                tx.get("comment", ""), owner,
            ))

    def get_transactions(self, days: int = 30, only_expenses: bool = True, owner: str = None) -> list:
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        query = "SELECT * FROM transactions WHERE time >= ?"
        params = [since]
        if only_expenses:
            query += " AND amount < 0"
        if owner:
            query += " AND owner = ?"
            params.append(owner)
        query += " ORDER BY time DESC"
        with self.conn() as con:
            return [dict(r) for r in con.execute(query, params).fetchall()]

    def get_categories_summary(self, days: int = 30, owner: str = None) -> list:
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        query = """
            SELECT category, COUNT(*) as count, SUM(ABS(amount)) as total
            FROM transactions
            WHERE time >= ? AND amount < 0 AND category != '💰 Надходження'
        """
        params = [since]
        if owner:
            query += " AND owner = ?"
            params.append(owner)
        query += " GROUP BY category ORDER BY total DESC"
        with self.conn() as con:
            return [dict(r) for r in con.execute(query, params).fetchall()]

    def get_total_spent(self, days: int = 30, owner: str = None) -> int:
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        query = "SELECT SUM(ABS(amount)) as total FROM transactions WHERE time >= ? AND amount < 0"
        params = [since]
        if owner:
            query += " AND owner = ?"
            params.append(owner)
        with self.conn() as con:
            row = con.execute(query, params).fetchone()
            return row["total"] or 0

    def get_top_spending(self, days: int = 30, limit: int = 5, owner: str = None) -> list:
        """Топ витрат — конкретні транзакції, не місця"""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        query = """
            SELECT description, category, SUM(ABS(amount)) as total, COUNT(*) as count
            FROM transactions
            WHERE time >= ? AND amount < 0 AND category != '💰 Надходження'
        """
        params = [since]
        if owner:
            query += " AND owner = ?"
            params.append(owner)
        query += " GROUP BY description ORDER BY total DESC LIMIT ?"
        params.append(limit)
        with self.conn() as con:
            return [dict(r) for r in con.execute(query, params).fetchall()]

    def save_pending_classification(self, tx_id: str, owner: str, description: str, amount: int):
        with self.conn() as con:
            con.execute(
                "INSERT OR IGNORE INTO pending_classifications (tx_id, owner, description, amount) VALUES (?,?,?,?)",
                (tx_id, owner, description, amount)
            )

    def get_pending_classifications(self, owner: str) -> list:
        with self.conn() as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM pending_classifications WHERE owner = ? ORDER BY asked_at",
                (owner,)
            ).fetchall()]

    def resolve_pending_classification(self, tx_id: str, category: str):
        with self.conn() as con:
            con.execute("DELETE FROM pending_classifications WHERE tx_id = ?", (tx_id,))
            con.execute("UPDATE transactions SET category = ? WHERE id = ?", (category, tx_id))

    def save_custom_keyword(self, keyword: str, category: str, owner: str):
        with self.conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO custom_keywords (keyword, category, added_by) VALUES (?,?,?)",
                (keyword.lower(), category, owner)
            )

    def get_transaction_by_id(self, tx_id: str) -> dict | None:
        with self.conn() as con:
            row = con.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            return dict(row) if row else None

    def get_custom_keywords(self, owner: str) -> list[tuple[str, str]]:
        with self.conn() as con:
            rows = con.execute(
                "SELECT keyword, category FROM custom_keywords WHERE added_by = ?", (owner,)
            ).fetchall()
            return [(r["keyword"], r["category"]) for r in rows]
