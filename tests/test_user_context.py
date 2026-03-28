import os, pytest
os.environ["MY_TELEGRAM_ID"] = "111"
os.environ["PARTNER_TELEGRAM_ID"] = "222"

import importlib
import user_context
importlib.reload(user_context)  # pick up env vars set above

from user_context import get_owner

def test_main_user():
    assert get_owner(111) == "me"

def test_partner():
    assert get_owner(222) == "partner"

def test_unknown_returns_none():
    assert get_owner(999) is None

def test_zero_id_returns_none():
    assert get_owner(0) is None
