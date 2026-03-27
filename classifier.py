from groq import Groq


MCC_CATEGORIES = {
    5411: "🛒 Супермаркет", 5412: "🛒 Супермаркет", 5422: "🛒 Супермаркет",
    5499: "🛒 Супермаркет", 5441: "🍬 Солодощі", 5451: "🥛 Молочні",
    5812: "☕ Кафе/Ресторани", 5813: "🍺 Бари", 5814: "🍔 Фастфуд",
    4111: "🚇 Транспорт", 4121: "🚕 Таксі", 4131: "🚌 Автобус",
    7523: "🅿️ Парковка", 5541: "⛽ АЗС", 5542: "⛽ АЗС",
    7832: "🎬 Кіно", 7922: "🎭 Розваги", 7999: "🎮 Розваги", 5735: "🎵 Музика",
    5912: "💊 Аптека", 8011: "🏥 Медицина", 8021: "🦷 Стоматологія",
    7230: "💅 Краса", 7298: "💆 Спа",
    5600: "👗 Одяг", 5611: "👗 Одяг", 5621: "👗 Одяг",
    5631: "👗 Одяг", 5641: "👗 Одяг", 5651: "👗 Одяг", 5661: "👗 Одяг",
    5045: "💻 Техніка", 5734: "💻 Техніка", 4814: "📱 Зв'язок",
    5993: "🚬 Тютюн",
}

VALID_CATEGORIES = [
    "🛒 Супермаркет", "☕ Кафе/Ресторани", "🍔 Фастфуд", "🍺 Бари",
    "🚕 Таксі", "🚇 Транспорт", "⛽ АЗС", "💊 Аптека", "🏥 Медицина",
    "👗 Одяг", "💅 Краса", "🎮 Розваги", "🎬 Кіно", "💻 Техніка",
    "📱 Зв'язок", "🚬 Тютюн/Алкоголь", "🏠 Комунальні", "💡 Підписки",
    "🎓 Освіта", "✈️ Подорожі", "🐾 Тварини", "💰 Перекази", "❓ Інше",
]


class Classifier:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
        self._cache = {}

    def classify(self, tx: dict) -> str:
        mcc = tx.get("mcc", 0)
        if mcc in MCC_CATEGORIES:
            return MCC_CATEGORIES[mcc]

        description = tx.get("description", "")
        comment = tx.get("comment", "")
        amount = abs(tx.get("amount", 0)) / 100

        cache_key = f"{description}_{mcc}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        category = self._classify_with_ai(description, comment, mcc, amount)
        self._cache[cache_key] = category
        return category

    def _classify_with_ai(self, description: str, comment: str, mcc: int, amount: float) -> str:
        categories_list = "\n".join(VALID_CATEGORIES)
        prompt = f"""Визнач категорію для банківської транзакції. Відповідай ЛИШЕ одним рядком — точною назвою категорії зі списку.

Транзакція: "{description}" | MCC: {mcc} | {amount:.0f} грн

Список категорій (відповідай ТОЧНО як написано):
{categories_list}"""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                max_tokens=30,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            result = response.choices[0].message.content.strip()
            # Знаходимо найближчу категорію зі списку
            for cat in VALID_CATEGORIES:
                if cat in result or result in cat:
                    return cat
            return "❓ Інше"
        except Exception:
            return "❓ Інше"
