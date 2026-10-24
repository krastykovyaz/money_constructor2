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


def try_parse_rate(value):
    try:
        return parse_rate(value)
    except (TypeError, ValueError):
        return None


def updated_at_line(now=None):
    import pytz
    from datetime import datetime
    now = now or datetime.now(pytz.timezone("Europe/Moscow"))
    return f"🕒 Обновлено: {now:%H:%M} МСК\n"


class ConversationState:
    """Per-chat conversation state shared across handler threads; entries expire so abandoned flows don't pile up."""

    def __init__(self, ttl_seconds=3600):
        import threading
        self._ttl = ttl_seconds
        self._items = {}
        self._lock = threading.Lock()

    def _purge(self, now):
        for key in [k for k, (ts, _) in self._items.items() if now - ts > self._ttl]:
            del self._items[key]

    def set(self, key, value):
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            self._items[key] = (now, value)

    def get(self, key, default=None):
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None or now - entry[0] > self._ttl:
                self._items.pop(key, None)
                return default
            return entry[1]

    def pop(self, key, default=None):
        now = time.monotonic()
        with self._lock:
            entry = self._items.pop(key, None)
        if entry is None or now - entry[0] > self._ttl:
            return default
        return entry[1]
