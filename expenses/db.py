import sqlite3
from contextlib import contextmanager

from expenses.parser import DEFAULT_CATEGORIES


class ExpenseDB:
    def __init__(self, db_path: str):
        self.path = db_path
        self._init_tables()

    @contextmanager
    def conn(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _init_tables(self):
        with self.conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expense_date DATE NOT NULL,
                    category     TEXT NOT NULL,
                    description  TEXT,
                    amount       REAL NOT NULL,
                    currency     TEXT NOT NULL DEFAULT 'UAH',
                    rate_uah     REAL NOT NULL DEFAULT 1,
                    amount_uah   REAL NOT NULL,
                    source       TEXT
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS expense_categories (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name    TEXT NOT NULL,
                    UNIQUE(user_id, name)
                )
            """)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add_expense(self, user_id: int, expense_date: str, category: str,
                    description: str | None, amount: float, currency: str,
                    rate_uah: float, amount_uah: float, source: str) -> int:
        with self.conn() as con:
            cur = con.execute("""
                INSERT INTO expenses
                    (user_id, expense_date, category, description,
                     amount, currency, rate_uah, amount_uah, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, expense_date, category, description,
                  amount, currency, rate_uah, amount_uah, source))
            return cur.lastrowid

    def get_expense(self, expense_id: int, user_id: int) -> dict | None:
        with self.conn() as con:
            row = con.execute(
                "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
                (expense_id, user_id)
            ).fetchone()
            return dict(row) if row else None

    def delete_expense(self, expense_id: int, user_id: int) -> bool:
        with self.conn() as con:
            return con.execute(
                "DELETE FROM expenses WHERE id = ? AND user_id = ?",
                (expense_id, user_id)
            ).rowcount > 0

    def get_history(self, user_id: int, offset: int = 0, limit: int = 10) -> list:
        with self.conn() as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM expenses WHERE user_id = ? "
                "ORDER BY expense_date DESC, id DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset)
            ).fetchall()]

    def count_expenses(self, user_id: int) -> int:
        with self.conn() as con:
            return con.execute(
                "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
            ).fetchone()[0]

    def get_last_expense_id(self, user_id: int) -> int | None:
        with self.conn() as con:
            row = con.execute(
                "SELECT id FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,)
            ).fetchone()
            return row[0] if row else None

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self, user_id: int, days: int | None = None) -> dict:
        base = "FROM expenses WHERE user_id = ?"
        params: list = [user_id]
        if days:
            base += " AND expense_date >= date('now', ?)"
            params.append(f"-{days} days")

        with self.conn() as con:
            total_row = con.execute(
                f"SELECT COUNT(*) as cnt, SUM(amount_uah) as total {base}", params
            ).fetchone()

            by_currency = [dict(r) for r in con.execute(
                f"SELECT currency, SUM(amount) as total {base} GROUP BY currency ORDER BY total DESC",
                params
            ).fetchall()]

            by_category = [dict(r) for r in con.execute(
                f"SELECT category, SUM(amount_uah) as total {base} "
                f"GROUP BY category ORDER BY total DESC",
                params
            ).fetchall()]

        count = total_row["cnt"] or 0
        total = total_row["total"] or 0.0
        return {
            "count": count,
            "total": total,
            "avg": total / count if count else 0.0,
            "by_currency": by_currency,
            "by_category": by_category,
        }

    # ── Categories ────────────────────────────────────────────────────────────

    def get_custom_categories(self, user_id: int) -> list[str]:
        with self.conn() as con:
            return [r[0] for r in con.execute(
                "SELECT name FROM expense_categories WHERE user_id = ? ORDER BY name",
                (user_id,)
            ).fetchall()]

    def get_all_categories(self, user_id: int) -> list[str]:
        custom = self.get_custom_categories(user_id)
        return DEFAULT_CATEGORIES + [c for c in custom if c not in DEFAULT_CATEGORIES]

    def add_category(self, user_id: int, name: str) -> bool:
        try:
            with self.conn() as con:
                con.execute(
                    "INSERT OR IGNORE INTO expense_categories (user_id, name) VALUES (?, ?)",
                    (user_id, name)
                )
            return True
        except Exception:
            return False
