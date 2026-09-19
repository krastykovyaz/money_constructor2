import importlib

import pytest

# Every top-level bot/scraper script in the repo. Importing each one with a
# dummy .env (see conftest.py) catches syntax errors, missing dependencies,
# and code that runs network/blocking calls at import time instead of under
# `if __name__ == '__main__':` — all real incidents in this repo's history.
SCRIPTS = [
    "accounter_bot",
    "accounter_bot_v2",
    "all_exchange",
    "binance_trade",
    "bot_utils",
    "crypto_currency",
    "currency_parser",
    "exchange_ligov_fintex_cbr_crypto",
    "form_post",
    "get_profile",
    "google_finance",
    "investing_parser",
    "ligovka",
    "moscow_trade",
    "p2p_binance",
    "profit_calculation",
    "registration_bot",
    "sber_excange_bot",
    "sberexchange_bot",
    "send_message_tg",
]


@pytest.mark.parametrize("module_name", SCRIPTS)
def test_script_imports_cleanly(module_name):
    importlib.import_module(module_name)
