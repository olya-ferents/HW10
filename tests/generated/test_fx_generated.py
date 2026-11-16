"""Unit-тести для app/engines/fx.py.

Модуль fx.py залежить від app.engines.policy (курси, тіри, ліміти, комісії).
Щоб тести були ізольованими й детермінованими (і не залежали від реальних
значень policy, які можуть змінюватись), ми підміняємо потрібні атрибути
policy через monkeypatch фіктивними, але реалістичними даними.
"""
import pytest

from app.engines import fx, policy


RATES = {"EUR": 1.0, "USD": 0.9, "GBP": 1.15}
TIERS = {"basic", "premium"}
ALLOWANCE = {"basic": 100.0, "premium": 1000.0}
SPREAD = {"basic": 2.0, "premium": 0.5}
TRANSFER_FEES = {
    "sepa": (0.5, 0.0),
    "swift": (5.0, 1.5),
}


def fake_to_eur(amount, currency):
    return amount * RATES[currency]


@pytest.fixture(autouse=True)
def fake_policy(monkeypatch):
    monkeypatch.setattr(policy, "RATES_TO_EUR", RATES)
    monkeypatch.setattr(policy, "TIERS", TIERS)
    monkeypatch.setattr(policy, "FX_FREE_MONTHLY_ALLOWANCE_EUR", ALLOWANCE)
    monkeypatch.setattr(policy, "FX_SPREAD_PCT", SPREAD)
    monkeypatch.setattr(policy, "TRANSFER_FEES", TRANSFER_FEES)
    monkeypatch.setattr(policy, "to_eur", fake_to_eur)


class TestMidRate:
    def test_known_pair(self):
        assert fx.mid_rate("USD", "EUR") == pytest.approx(RATES["USD"] / RATES["EUR"])

    def test_same_currency_is_one(self):
        assert fx.mid_rate("USD", "USD") == pytest.approx(1.0)

    def test_unknown_from_currency(self):
        with pytest.raises(ValueError, match="XXX"):
            fx.mid_rate("XXX", "EUR")

    def test_unknown_to_currency(self):
        with pytest.raises(ValueError, match="YYY"):
            fx.mid_rate("EUR", "YYY")


class TestQuoteValidation:
    def test_unknown_tier_raises(self):
        with pytest.raises(ValueError, match="unknown_tier"):
            fx.quote(100, "USD", "EUR", "unknown_tier")

    def test_unknown_currency_raises(self):
        with pytest.raises(ValueError):
            fx.quote(100, "ZZZ", "EUR", "basic")


class TestQuoteWithinAllowance:
    def test_no_spread_when_within_allowance(self):
        q = fx.quote(10, "USD", "EUR", "basic", allowance_used_eur=0.0)
        assert q.allowance_applied is True
        assert q.spread_pct == 0.0
        assert q.spread_amount == pytest.approx(0.0)
        assert q.final_amount == pytest.approx(q.gross_amount)

    def test_gross_amount_uses_mid_rate(self):
        q = fx.quote(10, "USD", "EUR", "basic")
        expected_rate = RATES["USD"] / RATES["EUR"]
        assert q.mid_rate == pytest.approx(expected_rate)
        assert q.gross_amount == pytest.approx(10 * expected_rate)

    def test_override_ignored_when_within_allowance(self):
        q = fx.quote(10, "USD", "EUR", "basic", spread_pct_override=50.0)
        assert q.spread_pct == 0.0
        assert q.spread_amount == pytest.approx(0.0)

    def test_allowance_fields_echoed(self):
        q = fx.quote(10, "USD", "EUR", "basic", allowance_used_eur=5.0)
        assert q.allowance_total_eur == ALLOWANCE["basic"]
        assert q.allowance_used_before_eur == 5.0


class TestQuoteOverAllowance:
    def test_default_spread_applied(self):
        # amount_eur = 200 * 0.9 = 180 > allowance(basic)=100
        q = fx.quote(200, "USD", "EUR", "basic", allowance_used_eur=0.0)
        assert q.allowance_applied is False
        assert q.spread_pct == SPREAD["basic"]
        expected_spread = q.gross_amount * SPREAD["basic"] / 100.0
        assert q.spread_amount == pytest.approx(expected_spread)
        assert q.final_amount == pytest.approx(q.gross_amount - expected_spread)

    def test_allowance_already_used_up(self):
        q = fx.quote(1, "USD", "EUR", "basic", allowance_used_eur=100.0)
        assert q.allowance_applied is False
        assert q.spread_pct == SPREAD["basic"]

    def test_override_spread_applied_when_over_allowance(self):
        q = fx.quote(200, "USD", "EUR", "basic", spread_pct_override=9.0)
        assert q.spread_pct == 9.0
        assert q.spread_amount == pytest.approx(q.gross_amount * 9.0 / 100.0)


class TestQuotePartialAllowance:
    def test_partial_allowance_within_limit_has_no_spread(self):
        q = fx.quote(10, "USD", "EUR", "basic", allowance_used_eur=0.0,
                     partial_allowance=True)
        assert q.spread_amount == pytest.approx(0.0)

    def test_partial_allowance_splits_charged_share(self):
        # amount_eur = 100*0.9 = 90, remaining allowance = 100-50 = 50
        # charged_eur = 90-50 = 40, charged_share = 40/90
        q = fx.quote(100, "USD", "EUR", "basic", allowance_used_eur=50.0,
                     partial_allowance=True)
        amount_eur = 100 * RATES["USD"]
        remaining_eur = ALLOWANCE["basic"] - 50.0
        charged_eur = amount_eur - remaining_eur
        charged_share = charged_eur / amount_eur
        expected_spread = q.gross_amount * charged_share * SPREAD["basic"] / 100.0
        assert q.allowance_applied is False
        assert q.spread_amount == pytest.approx(expected_spread)
        assert q.final_amount == pytest.approx(q.gross_amount - expected_spread)

    def test_partial_allowance_fully_over_limit(self):
        # allowance already fully used -> remaining_eur = 0 -> charged_share = 1
        q = fx.quote(100, "USD", "EUR", "basic", allowance_used_eur=100.0,
                     partial_allowance=True)
        expected_spread = q.gross_amount * SPREAD["basic"] / 100.0
        assert q.spread_amount == pytest.approx(expected_spread)

    def test_partial_allowance_zero_amount_no_division_error(self):
        q = fx.quote(0, "USD", "EUR", "basic", allowance_used_eur=100.0,
                     partial_allowance=True)
        assert q.spread_amount == pytest.approx(0.0)
        assert q.final_amount == pytest.approx(0.0)


class TestFxQuoteAsDict:
    def test_rounds_float_fields(self):
        q = fx.quote(1 / 3, "USD", "EUR", "basic")
        d = q.as_dict()
        assert d["amount"] == round(1 / 3, 6)
        assert d["mid_rate"] == round(q.mid_rate, 6)

    def test_keeps_non_float_fields_untouched(self):
        q = fx.quote(10, "USD", "EUR", "basic")
        d = q.as_dict()
        assert d["from_currency"] == "USD"
        assert d["to_currency"] == "EUR"
        assert d["tier"] == "basic"
        assert d["allowance_applied"] is True


class TestTransferFee:
    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="bogus"):
            fx.transfer_fee(100.0, "bogus")

    def test_flat_only_fee(self):
        result = fx.transfer_fee(100.0, "sepa")
        assert result == {
            "transfer_type": "sepa",
            "amount_eur": 100.0,
            "flat_fee_eur": 0.5,
            "percent_fee": 0.0,
            "total_fee_eur": 0.5,
        }

    def test_flat_plus_percent_fee(self):
        result = fx.transfer_fee(200.0, "swift")
        flat, pct = TRANSFER_FEES["swift"]
        expected_total = round(flat + 200.0 * pct / 100.0, 2)
        assert result["total_fee_eur"] == expected_total
        assert result["flat_fee_eur"] == flat
        assert result["percent_fee"] == pct

    def test_fee_rounded_to_two_decimals(self):
        monkey_fee = {"odd": (0.001, 0.333)}
        import app.engines.policy as pol
        pol.TRANSFER_FEES = monkey_fee
        result = fx.transfer_fee(100.0, "odd")
        assert result["total_fee_eur"] == round(0.001 + 100.0 * 0.333 / 100.0, 2)
