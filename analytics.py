from groq import Groq
from db import Database


SYSTEM_PROMPT = """Ти — Моноботик, жорсткий але справедливий фінансовий друг.
Говориш як близька людина: прямо, з підйобами, але по-доброму. Молодіжний стиль, без корпоративщини.
Знаєш витрати користувача і можеш коментувати їх. Пиши коротко, їдко, з емодзі. Тільки українська."""


class Analytics:
    def __init__(self, db: Database, api_key: str):
        self.db = db
        self.client = Groq(api_key=api_key)
        # Історія чату: {user_id: [{"role": ..., "content": ...}]}
        self._chat_history: dict = {}

    def _fmt(self, kopecks: int) -> str:
        return f"{abs(kopecks) / 100:,.0f}₴".replace(",", " ")

    def _finance_context(self) -> str:
        total = self.db.get_total_spent(days=30)
        categories = self.db.get_categories_summary(days=30)
        top = self.db.get_top_merchants(days=30, limit=3)

        cats = "\n".join([
            f"- {c['category']}: {self._fmt(c['total'])} ({c['count']} разів)"
            for c in categories[:8]
        ])
        merchants = "\n".join([
            f"- {m['description']}: {self._fmt(m['total'])}"
            for m in top
        ])
        return (
            f"Витрати за місяць: {self._fmt(total)}\n"
            f"Категорії:\n{cats}\n"
            f"Топ місць:\n{merchants}"
        )

    def monthly_stats(self) -> str:
        total = self.db.get_total_spent(days=30)
        categories = self.db.get_categories_summary(days=30)
        top = self.db.get_top_merchants(days=30, limit=5)
        per_day = total // 30

        lines = [
            "💳 МІСЯЦЬ У ЦИФРАХ\n",
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
            lines.append("\n— Улюблені місця —")
            medals = ["🥇", "🥈", "🥉", "4.", "5."]
            for i, m in enumerate(top):
                lines.append(f"{medals[i]} {m['description']}  {self._fmt(m['total'])}")

        lines.append("\n/roast — отримати по щці   /advice — план порятунку")
        return "\n".join(lines)

    def weekly_stats(self) -> str:
        total = self.db.get_total_spent(days=7)
        categories = self.db.get_categories_summary(days=7)
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

    def categories_breakdown(self) -> str:
        categories = self.db.get_categories_summary(days=30)
        total = self.db.get_total_spent(days=30)

        lines = ["🗂 ПОВНИЙ РОЗКЛАД · 30 ДНІВ\n"]

        for cat in categories:
            pct = (cat["total"] / total * 100) if total else 0
            filled = round(pct / 5)
            bar = "█" * filled + "░" * (20 - filled)
            lines.append(f"{cat['category']}  ·  {pct:.0f}%")
            lines.append(f"{bar}")
            lines.append(f"  {self._fmt(cat['total'])}  ·  {cat['count']} транзакцій\n")

        return "\n".join(lines)

    async def roast(self) -> str:
        context = self._finance_context()

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=700,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Ось мої витрати за місяць:\n{context}\n\n"
                    "Зроби жорсткий розбір польотів: знайди найдичніші витрати, "
                    "прокоментуй конкретні цифри з сарказмом, порівняй з чимось реальним "
                    "(скільки це піц/поїздок/etc). Закінч одною конкретною порадою. "
                    "Без вступів, одразу до справи. Максимум 250 слів."
                )}
            ]
        )
        return "🔥 РОЗБІР ПОЛЬОТІВ\n\n" + response.choices[0].message.content.strip()

    async def advice(self) -> str:
        context = self._finance_context()
        prev_total = self.db.get_total_spent(days=60) - self.db.get_total_spent(days=30)

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=600,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Мої витрати:\n{context}\n"
                    f"Попередній місяць приблизно: {self._fmt(prev_total)}\n\n"
                    "Дай конкретний план: 1) топ-3 де скоротити з конкретними сумами "
                    "2) що не чіпати 3) одна дія на цьому тижні. "
                    "Без води, тільки конкретика. Максимум 200 слів."
                )}
            ]
        )
        return "💡 ПЛАН ДІЙ\n\n" + response.choices[0].message.content.strip()

    async def chat(self, user_id: int, message: str) -> str:
        if user_id not in self._chat_history:
            context = self._finance_context()
            self._chat_history[user_id] = [
                {"role": "system", "content": (
                    f"{SYSTEM_PROMPT}\n\nПоточні фінанси користувача:\n{context}"
                )}
            ]

        self._chat_history[user_id].append({"role": "user", "content": message})

        # Тримаємо не більше 20 повідомлень щоб не переповнити контекст
        history = self._chat_history[user_id]
        if len(history) > 21:
            self._chat_history[user_id] = [history[0]] + history[-20:]

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=500,
            messages=self._chat_history[user_id]
        )

        reply = response.choices[0].message.content.strip()
        self._chat_history[user_id].append({"role": "assistant", "content": reply})
        return reply
