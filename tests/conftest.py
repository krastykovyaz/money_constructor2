import os

# The bot scripts read their token via os.environ[...] at import time.
# Set harmless placeholders before any test module imports them, so tests
# don't depend on a real .env file being present.
for _var in (
    "EXCHANGE_DESK_BOT_TOKEN",
    "ALL_EXCHANGE_BOT_TOKEN",
    "LEGACY_ACCOUNTER_BOT_TOKEN",
    "ACCOUNTER_BOT_TOKEN",
    "LIGOVKA_BOT_TOKEN",
    "FINANCIAL_AGENT_BOT_TOKEN",
    "SBER_EXCHANGE_BOT_TOKEN",
    "CURRENCY_PARSER_BOT_TOKEN",
    "CRYPTO_CURRENCY_BOT_TOKEN",
):
    # python-telegram-bot's Bot() validates the token shape (digits, a
    # colon, len(left) >= 3) at construction time for scripts that build a
    # Bot at import time — needs to look plausible, not just non-empty.
    os.environ.setdefault(_var, "123456789:test-token")
