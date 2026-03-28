# Monobot v2 — Design Spec
**Date:** 2026-03-28

## Overview

Refactor and extend a Telegram finance bot that tracks Monobank (and PrivatBank) expenses for two users (main + partner). Key goals: multi-user personalization, PrivatBank CSV import, pattern detection, interactive classification, harsher personality, and webhook security.

---

## 1. File Structure

### New layout
```
bot.py              — init + wire-up only (< 80 lines)
handlers.py         — all command/message handlers (moved from bot.py)
user_context.py     — maps Telegram user_id → owner ("me"/"partner"/None)
patterns.py         — pattern detector (frequency, night spending, big amounts, habits)
privat_csv.py       — Privat24 CSV/XLS parser (replaces privatbank.py)
classifier.py       — unchanged logic + pending queue for unclassified
analytics.py        — unchanged logic + owner-aware context
db.py               — + pending_classifications and custom_keywords tables
notifier.py         — + pattern alert formatting
webhook_server.py   — + Monobank signature verification
```

### Deleted
- `privatbank.py` — replaced by `privat_csv.py`

### New env vars
```
MY_TELEGRAM_ID=<int>        # main user's Telegram ID
PARTNER_TELEGRAM_ID=<int>   # partner's Telegram ID
```

---

## 2. Multi-User Identification

### `user_context.py`
```python
def get_owner(telegram_id: int) -> str | None:
    if telegram_id == int(os.getenv("MY_TELEGRAM_ID", 0)): return "me"
    if telegram_id == int(os.getenv("PARTNER_TELEGRAM_ID", 0)): return "partner"
    return None  # unknown user — bot ignores silently
```

### Behavior changes
- Every handler calls `get_owner(update.effective_user.id)` first
- If `None` → silent ignore (security: bot doesn't respond to strangers)
- `/stats`, `/week`, `/categories`, `/roast`, `/advice` → filtered by owner
- `chat()` → finance context built for that owner's data
- `/family` → available to both, shows both + combined
- "— Я —" hardcoded label replaced with "— Твої витрати —"
- `/syncpartner` remains accessible only (implied by partner having no sync command)

---

## 3. PrivatBank CSV Import

### Removes
- `privatbank.py` (XML merchant API — requires business credentials, unavailable for personal accounts)
- `PRIVAT_MERCHANT_ID`, `PRIVAT_PASSWORD`, `PRIVAT_CARD` env vars

### Adds: `privat_csv.py`
Parses Privat24 statement export. Privat24 exports as XLS with columns:
`Дата | Час | Категорія | Картка | Отримувач | Сума | Валюта | Залишок | Валюта залишку`

```python
def parse_privat_csv(file_bytes: bytes, filename: str) -> list[dict]:
    # supports .csv and .xls/.xlsx
    # normalizes to Monobank transaction format
    # generates deterministic IDs: f"pb_{date}_{amount}_{description_hash}"
    # filters only UAH, only expenses (amount < 0)
```

### Bot changes
- `handlers.py` adds `document_handler` — triggers on `.csv`/`.xls`/`.xlsx` files
- Bot downloads file, calls `parse_privat_csv()`, saves via existing `_do_sync` logic
- `/syncprivat` command now sends instructions: how to export from Privat24 app

---

## 4. Pattern Detection (`patterns.py`)

### Patterns tracked
| Pattern | Trigger condition | Message example |
|---------|------------------|-----------------|
| High frequency | 3+ transactions same category today | "4 кави за день. серйозно?" |
| Night spending | transaction between 23:00–05:00 | "2:47 ночі. ти шо робиш?" |
| Big amount | > 2× average for that category (last 30d) | "це в 3 рази більше ніж зазвичай тут" |
| Daily habit | same merchant 5+ consecutive days | "щодня тут вже 6 днів поспіль" |

### API
```python
def check_patterns(db: Database, tx: dict, category: str, owner: str) -> list[str]:
    # returns list of pattern alert strings (empty if none triggered)
```

### Integration points
1. **Webhook** (`webhook_server.py`): after saving transaction, call `check_patterns()`, append alerts to notification
2. **`/roast`** (`analytics.py`): call `get_pattern_summary(db, owner)` which scans last 30d for all patterns, includes in roast context

---

## 5. Interactive Classification

### Flow
1. Classifier returns "❓ Інше"
2. Transaction saved with `category = "❓ Інше"`
3. Bot sends message to `owner`'s Telegram: *"Шо це таке — 'Назва 150₴'? Напиши категорію"*
4. User replies → classifier maps to nearest `VALID_CATEGORIES` or saves as-is
5. `custom_keywords` table updated: `(keyword, category)` — keyword extracted from description
6. Transaction updated in DB

### DB tables
```sql
CREATE TABLE pending_classifications (
    tx_id TEXT PRIMARY KEY,
    owner TEXT,
    description TEXT,
    amount INTEGER,
    asked_at TEXT
);

CREATE TABLE custom_keywords (
    keyword TEXT,
    category TEXT,
    added_by TEXT,
    PRIMARY KEY (keyword, added_by)
);
```

### `classifier.py` changes
- `classify()` loads `custom_keywords` from DB before keyword matching
- `set_custom_keyword(db, keyword, category, owner)` — saves new mapping
- Pending state managed in `db.py`

### Conversation state
`handlers.py` uses a simple in-memory dict `_pending: dict[int, str]` mapping `user_id → tx_id`. When user sends a text message and `user_id` is in `_pending`, it's treated as a classification reply, not a chat message.

---

## 6. Bot Personality

### System prompt — rewritten
```
Ти — жорсткий фінансовий трекер. Говориш прямо, без прикрас.
Якщо витрата тупа — кажеш що вона тупа. Без "але ти заслуговуєш".
Короткі речення. Факти + різкий коментар. Тільки українська.
```

### `notifier.py` comment rewrites
- Before: *"ще одна кава якої ти 'заслуговуєш'"*
- After: *"четверта кава за день"* + pattern: *"ти нормальний?"*

### Notification format — simplified
```
💸 150₴  ·  Starbucks
☕ Кафе  ·  баланс 3 200₴
Цього місяця кафе: 2 100₴ (14 разів)
четверта кава сьогодні. може вистачить?
```

---

## 7. Webhook Security

### Current issue
No verification of Monobank webhook signature — any POST to `/webhook` is processed.

### Fix
Monobank signs requests with `X-Sign` header (base64 of Ed25519 signature over request body, using public key from `/personal/client-info`).

```python
async def verify_mono_signature(body: bytes, x_sign: str, public_key: str) -> bool:
    # Ed25519 verify using PyNaCl or cryptography library
```

- On startup: fetch public key via `monobank.get_client_info()`, cache it
- On each webhook request: verify signature, return 400 if invalid
- Add `PyNaCl` to `requirements.txt` for Ed25519 verification

---

## 8. Out of Scope

- Push notifications for partner's transactions to main user (not requested)
- Budget limits / alerts (not requested)
- Multi-bank webhooks for PrivatBank (no public personal API exists)
- Telegram inline keyboards for classification (text reply is sufficient)
