import time

import pytest

from bot_utils import escape_markdown_legacy, parse_rate, AlertCooldown


def test_parse_rate_plain():
    assert parse_rate("84.50") == 84.50


def test_parse_rate_comma_decimal():
    assert parse_rate("84,50") == 84.50


def test_parse_rate_thousands_space():
    assert parse_rate("1 234,56") == 1234.56


def test_parse_rate_accepts_float_input():
    # choose_exchange_rates() can hand back an already-parsed float; the
    # previous bare float(x).replace(...) crashed with
    # AttributeError: 'float' object has no attribute 'replace'.
    assert parse_rate(84.5) == 84.5


def test_parse_rate_rejects_garbage():
    with pytest.raises(ValueError):
        parse_rate("not-a-number")


def test_escape_markdown_legacy_escapes_special_chars():
    assert escape_markdown_legacy("USD_синий*") == "USD\\_синий\\*"


def test_escape_markdown_legacy_leaves_plain_text_alone():
    assert escape_markdown_legacy("EUR/RUB") == "EUR/RUB"


def test_escape_markdown_legacy_stringifies_input():
    assert escape_markdown_legacy(42) == "42"


def test_alert_cooldown_blocks_repeat_within_window():
    cooldown = AlertCooldown(cooldown_seconds=60)
    assert cooldown.should_send("usd") is True
    assert cooldown.should_send("usd") is False


def test_alert_cooldown_is_per_key():
    cooldown = AlertCooldown(cooldown_seconds=60)
    assert cooldown.should_send("usd") is True
    assert cooldown.should_send("eur") is True


def test_alert_cooldown_allows_after_window_elapses(monkeypatch):
    cooldown = AlertCooldown(cooldown_seconds=10)
    fake_time = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])
    assert cooldown.should_send("usd") is True
    fake_time[0] += 5
    assert cooldown.should_send("usd") is False
    fake_time[0] += 6
    assert cooldown.should_send("usd") is True


def _cbr_soup(xml):
    from bs4 import BeautifulSoup
    return BeautifulSoup(xml, "lxml-xml")


def test_cbr_valute_rate_divides_by_nominal():
    from bot_utils import cbr_valute_rate
    soup = _cbr_soup(
        '<ValCurs><Valute ID="R01035"><Nominal>1</Nominal><Value>110,9780</Value></Valute>'
        '<Valute ID="R01720"><Nominal>10</Nominal><Value>20,0000</Value></Valute></ValCurs>'
    )
    assert cbr_valute_rate(soup, "R01035") == pytest.approx(110.978)
    assert cbr_valute_rate(soup, "R01720") == pytest.approx(2.0)


def test_cbr_valute_rate_missing_or_malformed_returns_none():
    from bot_utils import cbr_valute_rate
    soup = _cbr_soup('<ValCurs><Valute ID="R01035"><Nominal>1</Nominal><Value>n/a</Value></Valute></ValCurs>')
    assert cbr_valute_rate(soup, "R01035") is None
    assert cbr_valute_rate(soup, "R99999") is None
