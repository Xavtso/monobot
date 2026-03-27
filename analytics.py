from groq import Groq
from db import Database


SYSTEM_PROMPT = """Ти — Моноботик, жорсткий фінансовий друг.
Говориш як близька людина: прямо, з підйобами, але по-доброму і з гумором. Молодіжний стиль, без корпоративщини.
Знаєш витрати користувача і можеш їх коментувати. Пиши коротко, їдко, з емодзі. Тільки українська мова."""


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

    def monthly_stats(self) -> str:
        text = self._build_stats_text()
        text += "\n\n/roast — отримати по щці   /advice — план порятунку"
        return text

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

        cats = "\n".join([
            f"- {c['category']}: {self._fmt(c['total'])} ({c['count']} разів)"
            for c in categories[:8]
        ])
        tops = "\n".join([
            f"- {t['description']} ({t['category']}): {self._fmt(t['total'])}"
            for t in top
        ])
        return f"Витрати за місяць: {self._fmt(total)}\nКатегорії:\n{cats}\nНайбільші витрати:\n{tops}"

    async def roast(self) -> str:
        context = self._finance_context()
        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=700,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Ось мої витрати:\n{context}\n\n"
                    "Зроби жорсткий розбір польотів: знайди найдичніші витрати, "
                    "прокоментуй конкретні цифри з сарказмом, порівняй з чимось реальним. "
                    "Закінч однією порадою. Без вступів. Максимум 250 слів."
                )}
            ]
        )
        return "🔥 РОЗБІР ПОЛЬОТІВ\n\n" + response.choices[0].message.content.strip()

    async def advice(self) -> str:
        context = self._finance_context()
        prev = self.db.get_total_spent(days=60) - self.db.get_total_spent(days=30)
        response = self.client.chat.completions.create(
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
        return "💡 ПЛАН ДІЙ\n\n" + response.choices[0].message.content.strip()

    async def chat(self, user_id: int, message: str) -> str:
        if user_id not in self._chat_history:
            context = self._finance_context()
            self._chat_history[user_id] = [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nФінанси:\n{context}"}
            ]

        self._chat_history[user_id].append({"role": "user", "content": message})

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
