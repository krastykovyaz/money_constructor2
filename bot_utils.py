import re
import time

_MARKDOWN_LEGACY_SPECIAL = re.compile(r'([_*`\[])')


def escape_markdown_legacy(text):
    """Escape text for Telegram's legacy parse_mode='Markdown'.

    Only '_', '*', '`' and '[' are special in legacy Markdown (unlike
    MarkdownV2, which escapes many more characters).
    """
    return _MARKDOWN_LEGACY_SPECIAL.sub(r'\\\1', str(text))


def parse_rate(value):
    return float(str(value).replace(',', '.').replace(' ', ''))


class AlertCooldown:
    """Gates repeated alerts for the same key to at most once per cooldown window."""

    def __init__(self, cooldown_seconds=300):
        self.cooldown_seconds = cooldown_seconds
        self._last_sent = {}

    def should_send(self, key):
        now = time.monotonic()
        last = self._last_sent.get(key)
        if last is not None and now - last < self.cooldown_seconds:
            return False
        self._last_sent[key] = now
        return True


def cbr_valute_rate(soup, valute_id):
    """Rub per 1 unit of a CBR XML_daily currency, or None if absent/malformed."""
    valute = soup.find('Valute', ID=valute_id)
    if valute is None:
        return None
    try:
        return parse_rate(valute.Value.text) / parse_rate(valute.Nominal.text)
    except (AttributeError, ValueError, ZeroDivisionError):
        return None


def validate_operator_chat_id(chat_id, bot_token):
    """Fail fast on a missing operator chat or the bot's own ID (Telegram bots can't message bots)."""
    if not chat_id:
        raise ValueError("OPERATOR_CHAT_ID is not set")
    try:
        chat_id = int(chat_id)
    except (TypeError, ValueError):
        raise ValueError("OPERATOR_CHAT_ID must be a numeric Telegram chat ID")
    if str(chat_id) == str(bot_token).split(":", 1)[0]:
        raise ValueError("OPERATOR_CHAT_ID is the bot's own ID; use the operator's chat ID")
    return chat_id


def telegram_send(token, chat_id, text, timeout=10):
    """POST sendMessage; returns (ok, error_description). Never logs or returns the URL/token."""
    import requests
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=timeout,
        )
    except requests.RequestException as e:
        return False, type(e).__name__
    if response.ok:
        return True, None
    try:
        return False, response.json().get("description", f"HTTP {response.status_code}")
    except ValueError:
        return False, f"HTTP {response.status_code}"
