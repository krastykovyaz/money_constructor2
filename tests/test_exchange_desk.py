import pytest

import exchange_ligov_fintex_cbr_crypto as desk


def test_choose_exchange_rates_does_not_alias_input_dicts():
    # Regression test: choose_exchange_rates() used to append the original
    # fintech dict by reference when there was no matching Ligovka rate.
    # update_message() then mutated that dict in place (item['purchase'] =
    # usd_rub), silently turning the cached string rate into a float and
    # crashing the next cycle's parse_rate() with
    # AttributeError: 'float' object has no attribute 'replace'.
    fintech_item = {"currency": "USD синий", "purchase": "84.50", "sale": "85.00"}
    fintech_data = [fintech_item]

    chosen = desk.choose_exchange_rates(fintech_data, ligovka_data=[])
    assert len(chosen) == 1
    chosen[0]["purchase"] = 999.0  # simulate update_message()'s in-place patch

    assert fintech_item["purchase"] == "84.50", (
        "choose_exchange_rates() must return copies, not references, "
        "or the shared rate cache gets corrupted"
    )


def test_choose_exchange_rates_combines_fintech_and_ligovka():
    fintech_data = [{"currency": "USD", "purchase": "85.00", "sale": "86.00"}]
    ligovka_data = [{"currency": "USD (от 1)", "purchase": "84.50", "sale": "86.50"}]

    chosen = desk.choose_exchange_rates(fintech_data, ligovka_data)

    assert len(chosen) == 1
    # sell side picks the higher (more favorable to the house) of the two
    assert chosen[0]["sale"] == 86.50
    # buy side picks the lower
    assert chosen[0]["purchase"] == 84.50


def test_round_buy_price_rounds_mid_fraction_to_half():
    assert desk.round_buy_price(84.35) == 84.5


def test_round_buy_price_rounds_low_fraction_to_whole():
    assert desk.round_buy_price(84.05) == 84.0


def test_round_sell_price_rounds_to_nearest_half():
    assert desk.round_sell_price(84.24) == 84.0
    assert desk.round_sell_price(84.26) == 84.5


def _rates(dollar=None, euro=None, usdt=None):
    return {"dollar": dollar, "euro": euro, "usdt": usdt}


def test_convert_currency_full_rates_returns_all_currencies():
    rates = _rates(
        dollar={"buy": 84.0, "sell": 85.0},
        euro={"buy": 96.0, "sell": 97.0},
        usdt={"buy": 84.0, "sell": 85.5},
    )
    results = desk.convert_currency(100, "eur", rates)
    assert results["rub"] == 9700
    assert results["usd"] == pytest.approx(9700 / 85.0)
    assert results["usdt"] == pytest.approx(9700 / 85.5)


def test_convert_currency_missing_from_currency_rate_returns_none():
    rates = _rates(dollar=None, euro=None, usdt=None)
    assert desk.convert_currency(100, "eur", rates) is None


def test_convert_currency_degrades_gracefully_when_one_rate_missing():
    # Regression test: convert_currency() used to require ALL currencies'
    # rates to be present and returned None for the whole calculation if
    # even one (e.g. USDT, sourced from Ligovka) was temporarily
    # unavailable — even for a plain EUR->RUB conversion that never
    # touched USDT.
    rates = _rates(
        dollar={"buy": 84.0, "sell": 85.0},
        euro={"buy": 96.0, "sell": 97.0},
        usdt=None,
    )
    results = desk.convert_currency(100, "eur", rates)
    assert results is not None
    assert results["rub"] == 9700
    assert results["usd"] == pytest.approx(9700 / 85.0)
    assert results["usdt"] is None


def test_format_calc_reply_flags_missing_currency():
    results = {"rub": 9700.0, "usd": 114.12, "usdt": None}
    text = desk.format_calc_reply(100, "eur", results)
    assert "114.12 USD" in text
    assert "USDT пока недоступен" in text
