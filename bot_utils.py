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
