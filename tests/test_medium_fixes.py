import datetime

import pytest

import all_exchange
import exchange_ligov_fintex_cbr_crypto as desk
import scrapers
from bot_utils import try_parse_rate, updated_at_line


def test_try_parse_rate():
    assert try_parse_rate("1 234,5") == 1234.5
    assert try_parse_rate(" 86.20\n") == 86.2
    assert try_parse_rate("—") is None and try_parse_rate(None) is None


def test_updated_at_line_formats_moscow_time():
    assert updated_at_line(datetime.datetime(2026, 10, 17, 9, 5)) == "🕒 Обновлено: 09:05 МСК\n"


class FakeDriver:
    def __init__(self, html, profile_dir):
        self.page_source, self.exchange_user_data_dir = html, profile_dir

    def get(self, url):
        pass

    def quit(self):
        pass


def test_fintech_rows_with_unparseable_rates_are_dropped(monkeypatch, tmp_path):
    # Regression: one "—" from the site used to abort the whole exchange_desk update cycle.
    html = """<table><tr><th>h</th></tr>
    <tr><td>USD синий</td><td>86,20</td><td>86.60</td><td>от 5000</td></tr>
    <tr><td>EUR</td><td>—</td><td>97.50</td><td>от 5000</td></tr></table>"""
    monkeypatch.setattr(scrapers, "get_driver", lambda: FakeDriver(html, str(tmp_path / "p")))
    monkeypatch.setattr(scrapers.time, "sleep", lambda s: None)
    monkeypatch.setattr(desk, "currency_cache", {"data": [], "updated_at": None})
    data = desk.get_currency_data_fintech()["data"]
    assert [row["currency"] for row in data] == ["USD синий"]


def test_ligovka_rows_with_unparseable_rates_are_dropped(monkeypatch):
    cells = "".join(f"<td>{x}</td>" for x in ("от 1", "x", "85,9", "87,4", "x", "96,3", "—", "x", "1,10", "1,13"))
    response = type("R", (), {"text": f"<table><tr>{cells}</tr></table>", "raise_for_status": lambda self: None})()
    monkeypatch.setattr(desk.session, "get", lambda *a, **k: response)
    rows = {r["currency"] for r in desk.get_currency_data_ligovka()}
    assert rows == {"USD (от 1)", "EUR/USD (от 1)"}


class FakeMessage:
    def __init__(self, text):
        self.text, self.chat_id, self.replies = text, 99, []
        self.from_user = type("U", (), {"username": "c", "first_name": "A", "id": 99})()

    def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeBot:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text):
        self.sent.append(text)


def _handle(module, text):
    message, bot = FakeMessage(text), FakeBot()
    module.handle_amount(type("U", (), {"message": message})(), type("C", (), {"bot": bot})())
    return message, bot


@pytest.mark.parametrize("module", [all_exchange, desk])
def test_number_without_active_flow_is_not_an_order(module):
    # Regression: any number typed by any user used to reach the operator as a "new order".
    module.user_data.pop(99)
    message, bot = _handle(module, "6000")
    assert bot.sent == [] and message.replies == [module.NO_ACTIVE_FLOW_HINT]


@pytest.mark.parametrize("module", [all_exchange, desk])
def test_order_flow_still_reaches_operator_and_clears_state(module):
    module.user_data.set(99, {"category": "euro_choice"})
    message, bot = _handle(module, "6000")
    assert len(bot.sent) == 1 and "6000" in bot.sent[0]
    assert module.user_data.get(99) is None


@pytest.mark.parametrize("module", [all_exchange, desk])
def test_invalid_amount_keeps_flow_open(module):
    module.user_data.set(99, {"category": "euro_choice"})
    message, bot = _handle(module, "abc")
    assert bot.sent == [] and module.user_data.get(99) == {"category": "euro_choice"}
    module.user_data.pop(99)
