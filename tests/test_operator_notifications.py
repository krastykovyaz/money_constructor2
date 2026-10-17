import pytest
import requests

import all_exchange
import bot_utils
from bot_utils import telegram_send, validate_operator_chat_id


class FakeResponse:
    def __init__(self, ok=True, status_code=200, payload=None):
        self.ok, self.status_code, self._payload = ok, status_code, payload or {}

    def json(self):
        return self._payload


def test_validate_rejects_missing_id():
    with pytest.raises(ValueError, match="not set"):
        validate_operator_chat_id(None, "123:abc")


def test_validate_rejects_non_numeric_id():
    with pytest.raises(ValueError, match="numeric"):
        validate_operator_chat_id("@someone", "123:abc")


def test_validate_rejects_the_bots_own_id():
    # Regression: exchange_desk defaulted to its own bot ID, and Telegram
    # answers "Forbidden: the bot can't send messages to the bot".
    with pytest.raises(ValueError, match="own ID"):
        validate_operator_chat_id("8773698197", "8773698197:token")


def test_validate_accepts_operator_id():
    assert validate_operator_chat_id("42", "123:abc") == 42


def test_telegram_send_reports_telegram_rejection(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(
        ok=False, status_code=403, payload={"description": "Forbidden: bot can't send messages to the bot"}))
    ok, error = telegram_send("123:secret", 1, "hi")
    assert ok is False and "Forbidden" in error


def test_telegram_send_never_leaks_token_on_network_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("https://api.telegram.org/bot123:secret/sendMessage failed")
    monkeypatch.setattr(requests, "post", boom)
    ok, error = telegram_send("123:secret", 1, "hi")
    assert ok is False and "secret" not in error


def test_telegram_send_ok(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse())
    assert telegram_send("123:abc", 1, "hi") == (True, None)


class FakeMessage:
    def __init__(self, text, username="client"):
        self.text, self.chat_id, self.replies = text, 7, []
        self.from_user = type("U", (), {"username": username, "first_name": "A", "id": 7})()

    def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeBot:
    def __init__(self, fail=False):
        self.fail, self.sent = fail, []

    def send_message(self, chat_id, text):
        if self.fail:
            raise RuntimeError("Forbidden")
        self.sent.append((chat_id, text))


def _run_all_exchange(fail):
    all_exchange.user_data[7] = {"category": "blue_choice"}
    message, bot = FakeMessage("6000"), FakeBot(fail=fail)
    all_exchange.handle_amount(
        type("Upd", (), {"message": message})(), type("Ctx", (), {"bot": bot})()
    )
    return message, bot


def test_all_exchange_confirms_order_only_after_delivery():
    message, bot = _run_all_exchange(fail=False)
    assert bot.sent and bot.sent[0][0] == all_exchange.OPERATOR_CHAT_ID
    assert message.replies == [f"✅ Заказ отправлен оператору - {all_exchange.OPERATOR_CONTACT}"]


def test_all_exchange_does_not_claim_success_when_delivery_fails():
    # Regression: the "order sent" reply used to go out before an unguarded send_message.
    message, bot = _run_all_exchange(fail=True)
    assert len(message.replies) == 1
    assert "Не удалось" in message.replies[0] and "✅" not in message.replies[0]
