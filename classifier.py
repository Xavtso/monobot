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

# Ключові слова — спрацьовують ДО виклику AI
KEYWORD_CATEGORIES = {
    "🎮 Розваги": [
        "playstation", "ps store", "ps5", "ps4", "xbox", "steam", "epic games",
        "nintendo", "google play games", "apple arcade", "twitch", "discord nitro",
        "gog.com", "ubisoft", "ea games", "blizzard",
    ],
    "💡 Підписки": [
        "netflix", "spotify", "apple music", "youtube premium", "youtube music",
        "google one", "icloud", "apple one", "hbo", "disney+", "paramount",
        "chatgpt", "openai", "midjourney", "adobe", "figma", "notion",
        "github", "jetbrains", "canva", "dropbox", "zoom",
    ],
    "🚕 Таксі": [
        "uber", "bolt", "uklon", "taxi", "таксі",
    ],
    "🍔 Фастфуд": [
        "mcdonald", "mcdonalds", "kfc", "burger king", "domino", "pizza",
        "піца", "суші", "sushi", "wok", "шаурма", "shawarma",
    ],
    "☕ Кафе/Ресторани": [
        "starbucks", "coffeeshop", "coffee", "кафе", "ресторан", "bistro",
        "pancake", "gelato", "морозиво",
    ],
    "🚇 Транспорт": [
        "київ метро", "metro", "kyiv metro", "маршрутка", "укрзалізниця",
        "ukrzaliznytsia", "bus", "автобус", "трамвай",
    ],
    "✈️ Подорожі": [
        "airbnb", "booking", "hotels", "hotel", "hostel", "ryanair",
        "wizzair", "wizz air", "mau", "скайап", "skyup",
    ],
    "🛒 Супермаркет": [
        "сільпо", "silpo", "атб", "atb", "novus", "новус", "ашан", "auchan",
        "metro cash", "фора", "fora", "варус", "varus", "евросеть",
    ],
    "💊 Аптека": [
        "аптека", "apteka", "pharmacy", "farmacia", "здоров'я",
    ],
    "⛽ АЗС": [
        "wog", "okko", "укрнафта", "shell", "socar", "азс", "gas station",
    ],
    "📦 Доставка": [
        "нова пошта", "nova poshta", "новапошта", "meest", "justin",
        "укрпошта", "glovo", "bolt food", "uber eats",
    ],
    "👗 Одяг": [
        "zara", "h&m", "hm", "bershka", "pull&bear", "reserved", "lcwaikiki",
        "adidas", "nike", "puma", "new balance", "shein", "answear",
    ],
    "💻 Техніка": [
        "apple store", "comfy", "foxtrot", "eldorado", "rozetka",
        "moyo", "citrus", "ябко",
    ],
    "📱 Зв'язок": [
        "kyivstar", "київстар", "vodafone", "lifecell", "life:)",
        "інтернет", "internet", "triolan", "datagroup",
    ],
    "🎓 Освіта": [
        "udemy", "coursera", "duolingo", "lingoda", "prometheus",
        "skillshare", "masterclass",
    ],
    "🐾 Тварини": [
        "зоомагазин", "pet shop", "ветеринар", "veterinar", "zoo",
    ],
    "🍺 Бари": [
        "bar ", "pub ", "паб", "бар", "brewery", "пивна",
    ],
}

VALID_CATEGORIES = [
    "🛒 Супермаркет", "☕ Кафе/Ресторани", "🍔 Фастфуд", "🍺 Бари",
    "🚕 Таксі", "🚇 Транспорт", "⛽ АЗС", "💊 Аптека", "🏥 Медицина",
    "👗 Одяг", "💅 Краса", "🎮 Розваги", "🎬 Кіно", "💻 Техніка",
    "📱 Зв'язок", "🚬 Тютюн/Алкоголь", "🏠 Комунальні", "💡 Підписки",
    "🎓 Освіта", "✈️ Подорожі", "🐾 Тварини", "💰 Перекази",
    "📦 Доставка", "❓ Інше",
]


class Classifier:
    def __init__(self, api_key: str, db=None):
        self.client = Groq(api_key=api_key)
        self.db = db
        self._cache = {}

    def classify(self, tx: dict, owner: str = "me", force: bool = False) -> str:
        mcc = tx.get("mcc", 0)
        if mcc in MCC_CATEGORIES:
            return MCC_CATEGORIES[mcc]

        description = tx.get("description", "").lower()
        comment = tx.get("comment", "").lower()
        text = f"{description} {comment}"

        # Custom keywords from DB (user-taught) — checked before built-ins
        if self.db:
            for kw, cat in self.db.get_custom_keywords(owner):
                if kw in text:
                    return cat

        # Built-in keyword matching
        for category, keywords in KEYWORD_CATEGORIES.items():
            if any(kw in text for kw in keywords):
                return category

        cache_key = f"{description}_{mcc}"
        if not force and cache_key in self._cache:
            return self._cache[cache_key]

        amount = abs(tx.get("amount", 0)) / 100
        date_str = ""
        if tx.get("time"):
            from datetime import datetime
            date_str = datetime.fromtimestamp(tx["time"]).strftime("%d.%m.%Y %H:%M")

        category = self._classify_with_ai(
            tx.get("description", ""), tx.get("comment", ""), mcc, amount, date_str
        )
        self._cache[cache_key] = category
        return category

    def _classify_with_ai(self, description: str, comment: str, mcc: int, amount: float,
                          date_str: str = "") -> str:
        categories_list = "\n".join(VALID_CATEGORIES)
        date_line = f" | дата: {date_str}" if date_str else ""
        prompt = f"""Визнач категорію для банківської транзакції. Відповідай ЛИШЕ одним рядком — точною назвою категорії зі списку нижче. Ніяких пояснень.

Транзакція: "{description}" | коментар: "{comment}" | MCC: {mcc} | {amount:.0f} грн{date_line}

Категорії:
{categories_list}"""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                max_tokens=20,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            result = response.choices[0].message.content.strip()
            for cat in VALID_CATEGORIES:
                if cat in result or result in cat:
                    return cat
            return "❓ Інше"
        except Exception:
            return "❓ Інше"
