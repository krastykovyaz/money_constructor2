import pytest

import all_exchange
import bot_utils
import exchange_ligov_fintex_cbr_crypto as desk
import scrapers
from bot_utils import ConversationState


class FakeDriver:
    def __init__(self, profile_dir):
        self.exchange_user_data_dir, self.quit_called = profile_dir, False

    def get(self, url):
        raise TimeoutError("page load")

    def quit(self):
        self.quit_called = True


def test_scrape_fintech_rows_cleans_up_chrome_even_on_failure(monkeypatch, tmp_path):
    profile = tmp_path / "exchange-chrome-x"
    profile.mkdir()
    driver = FakeDriver(str(profile))
    monkeypatch.setattr(scrapers, "get_driver", lambda: driver)
    with pytest.raises(TimeoutError):
        scrapers.scrape_fintech_rows()
    assert driver.quit_called and not profile.exists()


def test_both_bots_share_one_scraper_implementation():
    for name in ("get_cbr_currency", "get_currency_cnbc", "scrape_fintech_rows"):
        assert getattr(all_exchange, name) is getattr(scrapers, name)
        assert getattr(desk, name) is getattr(scrapers, name)


def test_conversation_state_set_get_pop():
    state = ConversationState()
    state.set(1, {"a": 1})
    assert state.get(1) == {"a": 1}
    assert state.pop(1) == {"a": 1}
    assert state.get(1) is None and state.pop(1) is None


def test_conversation_state_entries_expire_and_are_purged(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(bot_utils.time, "monotonic", lambda: now[0])
    state = ConversationState(ttl_seconds=60)
    state.set(1, "x")
    now[0] += 61
    assert state.get(1) is None
    state.set(2, "y")
    now[0] += 61
    state.set(3, "z")
    assert list(state._items) == [3]


class FakeMessage:
    def __init__(self, text):
        self.text, self.chat_id, self.replies = text, 77, []
        self.from_user = type("U", (), {"username": "secret_user", "first_name": "Secret", "id": 77})()

    def reply_text(self, text, **kwargs):
        self.replies.append(text)


@pytest.mark.parametrize("module", [all_exchange, desk])
def test_order_log_has_no_personal_data(module, capsys):
    module.user_data.set(77, {"category": "euro_choice"})
    bot = type("B", (), {"send_message": lambda self, chat_id, text: None})()
    module.handle_amount(type("U", (), {"message": FakeMessage("6000")})(), type("C", (), {"bot": bot})())
    out = capsys.readouterr().out
    assert "[ORDER] category=euro_choice amount=6000" in out
    assert "secret_user" not in out and "Secret" not in out and "77" not in out
