import os

import pytest

import all_exchange
import bot_utils
import exchange_ligov_fintex_cbr_crypto as desk
import scrapers
from bot_utils import ConversationState, try_parse_rate, updated_at_line


class FakeDriver:
    def __init__(self, html, profile_dir, fail_on_get=False):
        self.page_source, self.exchange_user_data_dir = html, profile_dir
        self.fail_on_get, self.quit_called = fail_on_get, False

    def get(self, url):
        if self.fail_on_get:
            raise TimeoutError("page load")

    def quit(self):
        self.quit_called = True


TABLE = """<table><tr><th>h</th></tr>
<tr><td>USD синий</td><td>86,20</td><td>86.60</td><td>от 5000</td></tr>
<tr><td>EUR</td><td>—</td><td>97.50</td><td>от 5000</td></tr>
<tr><td>USD синий</td><td>1</td><td>1</td><td>dup</td></tr></table>"""


def test_scrape_fintech_rows_skips_malformed_and_duplicate_rows(monkeypatch, tmp_path):
    # Regression: one "—" from the site used to abort the whole update cycle in exchange_desk.
    monkeypatch.setattr(scrapers, "get_driver", lambda: FakeDriver(TABLE, str(tmp_path)))
    monkeypatch.setattr(scrapers.time, "sleep", lambda s: None)
    rows = scrapers.scrape_fintech_rows()
    assert [r["currency"] for r in rows] == ["USD синий"]


def test_scrape_fintech_rows_always_cleans_up_chrome_profile(monkeypatch, tmp_path):
    profile = tmp_path / "exchange-chrome-x"
    profile.mkdir()
    driver = FakeDriver(TABLE, str(profile), fail_on_get=True)
    monkeypatch.setattr(scrapers, "get_driver", lambda: driver)
    monkeypatch.setattr(scrapers.time, "sleep", lambda s: None)
    with pytest.raises(TimeoutError):
        scrapers.scrape_fintech_rows()
    assert driver.quit_called and not profile.exists()


def test_ligovka_rows_with_unparseable_rates_are_dropped(monkeypatch):
    cells = lambda *c: "<tr>" + "".join(f"<td>{x}</td>" for x in c) + "</tr>"
    html = "<table>" + cells("от 1", "x", "85,9", "87,4", "x", "96,3", "—", "x", "1,10", "1,13") + "</table>"
    monkeypatch.setattr(desk.session, "get", lambda *a, **k: type("R", (), {
        "text": html, "raise_for_status": lambda self: None})())
    rows = {r["currency"]: r for r in desk.get_currency_data_ligovka()}
    assert "USD (от 1)" in rows and "EUR/USD (от 1)" in rows
    assert "EUR (от 1)" not in rows


def test_try_parse_rate():
    assert try_parse_rate("1 234,5") == 1234.5
    assert try_parse_rate("—") is None and try_parse_rate(None) is None


def test_updated_at_line_formats_moscow_time():
    import datetime
    assert updated_at_line(datetime.datetime(2026, 10, 17, 9, 5)) == "🕒 Обновлено: 09:05 МСК\n"


def test_conversation_state_set_get_pop():
    state = ConversationState()
    state.set(1, {"a": 1})
    assert state.get(1) == {"a": 1}
    assert state.pop(1) == {"a": 1}
    assert state.get(1) is None and state.pop(1) is None


def test_conversation_state_entries_expire(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(bot_utils.time, "monotonic", lambda: now[0])
    state = ConversationState(ttl_seconds=60)
    state.set(1, "x")
    now[0] += 61
    assert state.get(1) is None
    state.set(2, "y")
    state.set(3, "z")
    now[0] += 61
    state.set(4, "w")
    assert list(state._items) == [4]


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


@pytest.mark.parametrize("module", [all_exchange, desk])
def test_numeric_message_without_active_flow_is_not_an_order(module):
    # Regression: any number typed by any user used to ping the operator as a "new order".
    module.user_data.pop(99)
    message, bot = FakeMessage("6000"), FakeBot()
    module.handle_amount(type("U", (), {"message": message})(), type("C", (), {"bot": bot})())
    assert bot.sent == []
    assert message.replies == [module.NO_ACTIVE_FLOW_HINT]
