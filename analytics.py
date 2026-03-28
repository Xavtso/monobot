import asyncio
from datetime import datetime
from groq import Groq
from db import Database


SYSTEM_PROMPT = """Ти — жорсткий фінансовий трекер без цензури.
Говориш прямо, коротко, без прикрас і без виправдань.
Якщо витрата тупа — кажеш що вона тупа. Без "але ти заслуговуєш".
Факти + різкий коментар. Емодзі помірно. Тільки українська мова.
Не вигадуй даних — коментуй тільки те що є."""


class Analytics:
    def __init__(self, db: Database, api_key: str):
        self.db = db
        self.client = Groq(api_key=api_key)
        self._chat_history: dict = {}

    def _fmt(self, kopecks: int) -> str:
        return f"{abs(kopecks) / 100:,.0f}₴".replace(",", " ")

    def _build_stats_text(self, owner: str = None, label: str = "") -> str:
        total = self.db.get_total_spent(days=30, owner=owner)
        categories = self.db.get_categories_summary(days=30, owner=owner)
        top = self.db.get_top_spending(days=30, limit=5, owner=owner)
        per_day = total // 30

        title = f"💳 {label.upper()} · МІСЯЦЬ\n" if label else "💳 МІСЯЦЬ У ЦИФРАХ\n"
        lines = [
            title,
            f"Всього витрачено: {self._fmt(total)}",
            f"В день в середньому: {self._fmt(per_day)}\n",
            "— Категорії —",
        ]

        for cat in categories[:7]:
            pct = (cat["total"] / total * 100) if total else 0
            filled = round(pct / 10)
            bar = "●" * filled + "○" * (10 - filled)
            lines.append(f"{cat['category']}")
            lines.append(f"{bar}  {self._fmt(cat['total'])}  {pct:.0f}%")

        if top:
            lines.append("\n— Найбільші витрати —")
            medals = ["🥇", "🥈", "🥉", "4.", "5."]
            for i, t in enumerate(top):
                lines.append(f"{medals[i]} {t['description']}  {self._fmt(t['total'])}")

        return "\n".join(lines)

    def monthly_stats(self, owner: str = None) -> str:
        text = self._build_stats_text(owner=owner)
        text += "\n\n/roast — розбір польотів   /advice — план порятунку"
        return text

    def weekly_stats(self, owner: str = None) -> str:
        total = self.db.get_total_spent(days=7, owner=owner)
        categories = self.db.get_categories_summary(days=7, owner=owner)
        per_day = total // 7

        lines = [
            "📅 ТИЖДЕНЬ\n",
            f"За 7 днів: {self._fmt(total)}",
            f"В день: {self._fmt(per_day)}\n",
            "— Розклад —",
        ]
        for cat in categories[:8]:
            pct = (cat["total"] / total * 100) if total else 0
            lines.append(f"{cat['category']}  {self._fmt(cat['total'])}  {pct:.0f}%")
        return "\n".join(lines)

    def categories_breakdown(self, owner: str = None) -> str:
        categories = self.db.get_categories_summary(days=30, owner=owner)
        total = self.db.get_total_spent(days=30, owner=owner)

        lines = ["🗂 ПОВНИЙ РОЗКЛАД · 30 ДНІВ\n"]
        for cat in categories:
            pct = (cat["total"] / total * 100) if total else 0
            filled = round(pct / 5)
            bar = "█" * filled + "░" * (20 - filled)
            lines.append(f"{cat['category']}  ·  {pct:.0f}%")
            lines.append(f"{bar}")
            lines.append(f"  {self._fmt(cat['total'])}  ·  {cat['count']} транзакцій\n")
        return "\n".join(lines)

    def family_stats(self, partner_label: str = "партнер") -> str:
        my_total = self.db.get_total_spent(days=30, owner="me")
        partner_total = self.db.get_total_spent(days=30, owner="partner")
        combined = my_total + partner_total

        my_cats = self.db.get_categories_summary(days=30, owner="me")
        partner_cats = self.db.get_categories_summary(days=30, owner="partner")

        lines = [
            "👨‍👩‍ СІМЕЙНИЙ БЮДЖЕТ · МІСЯЦЬ\n",
            f"Разом витрачено: {self._fmt(combined)}\n",
            f"— Я ({self._fmt(my_total)}) —",
        ]
        for cat in my_cats[:5]:
            pct = (cat["total"] / my_total * 100) if my_total else 0
            lines.append(f"{cat['category']}  {self._fmt(cat['total'])}  {pct:.0f}%")

        lines.append(f"\n— {partner_label.capitalize()} ({self._fmt(partner_total)}) —")
        if partner_total:
            for cat in partner_cats[:5]:
                pct = (cat["total"] / partner_total * 100) if partner_total else 0
                lines.append(f"{cat['category']}  {self._fmt(cat['total'])}  {pct:.0f}%")
        else:
            lines.append("Ще немає даних — зроби /syncpartner")

        lines.append(f"\n— Разом —")
        all_cats = {}
        for c in my_cats + partner_cats:
            key = c["category"]
            all_cats[key] = all_cats.get(key, 0) + c["total"]
        for cat, total in sorted(all_cats.items(), key=lambda x: -x[1])[:5]:
            pct = (total / combined * 100) if combined else 0
            lines.append(f"{cat}  {self._fmt(total)}  {pct:.0f}%")

        return "\n".join(lines)

    def _finance_context(self, owner: str = None) -> str:
        total = self.db.get_total_spent(days=30, owner=owner)
        categories = self.db.get_categories_summary(days=30, owner=owner)
        top = self.db.get_top_spending(days=30, limit=3, owner=owner)
        transactions = self.db.get_transactions(days=30, owner=owner)

        cats = "\n".join([
            f"- {c['category']}: {self._fmt(c['total'])} ({c['count']} разів)"
            for c in categories[:8]
        ])
        tops = "\n".join([
            f"- {t['description']} ({t['category']}): {self._fmt(t['total'])}"
            for t in top
        ])

        tx_lines = []
        for tx in transactions[:40]:
            dt = datetime.fromtimestamp(tx["time"]) if tx.get("time") else None
            date_str = dt.strftime("%d.%m %H:%M") if dt else "—"
            amount = abs(tx["amount"]) / 100
            desc = tx.get("description") or "—"
            comment = tx.get("comment") or ""
            category = tx.get("category") or "❓ Інше"
            comment_part = f" ({comment})" if comment else ""
            tx_lines.append(f"- {date_str}  {desc}{comment_part}  {category}  -{amount:.0f}₴")

        tx_block = "\n".join(tx_lines) if tx_lines else "немає"

        return (
            f"Витрати за місяць: {self._fmt(total)}\n"
            f"Категорії:\n{cats}\n"
            f"Найбільші витрати:\n{tops}\n"
            f"Транзакції (останні 40, нові спершу):\n{tx_block}"
        )

    async def roast(self, owner: str = None) -> str:
        context = self._finance_context(owner=owner)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=700,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Ось витрати:\n{context}\n\n"
                        "Зроби жорсткий розбір польотів: знайди найдичніші витрати, "
                        "прокоментуй конкретні цифри з сарказмом, порівняй з чимось реальним. "
                        "Закінч однією конкретною порадою. Без вступів. Максимум 250 слів."
                    )}
                ]
            )
        )
        return "🔥 РОЗБІР ПОЛЬОТІВ\n\n" + response.choices[0].message.content.strip()

    async def advice(self, owner: str = None) -> str:
        context = self._finance_context(owner=owner)
        prev = self.db.get_total_spent(days=60, owner=owner) - self.db.get_total_spent(days=30, owner=owner)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=600,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Витрати:\n{context}\nПопередній місяць: {self._fmt(prev)}\n\n"
                        "Топ-3 де скоротити з конкретними сумами. Що не чіпати. "
                        "Одна дія на цьому тижні. Без води. Максимум 200 слів."
                    )}
                ]
            )
        )
        return "💡 ПЛАН ДІЙ\n\n" + response.choices[0].message.content.strip()

    async def chat(self, user_id: int, message: str, owner: str = "me") -> str:
        if user_id not in self._chat_history:
            context = self._finance_context(owner=owner)
            self._chat_history[user_id] = [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nФінанси:\n{context}"}
            ]

        self._chat_history[user_id].append({"role": "user", "content": message})

        history = self._chat_history[user_id]
        if len(history) > 21:
            self._chat_history[user_id] = [history[0]] + history[-20:]

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=500,
                messages=self._chat_history[user_id]
            )
        )
        reply = response.choices[0].message.content.strip()
        self._chat_history[user_id].append({"role": "assistant", "content": reply})
        return reply
