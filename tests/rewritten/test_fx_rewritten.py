import pytest

from app.engines import fx


def test_r01_usd_to_eur_uses_required_rate():
    assert fx.mid_rate("USD", "EUR") == pytest.approx(0.92)


def test_r02_tier2_reports_required_allowance_and_used_amount():
    q = fx.quote(100, "EUR", "USD", "tier2", allowance_used_eur=250)

    assert q.allowance_total_eur == pytest.approx(1000)
    assert q.allowance_used_before_eur == pytest.approx(250)


def test_r03_partial_allowance_charges_only_amount_above_remaining_limit():
    q = fx.quote(
        920, "EUR", "USD", "tier2",
        allowance_used_eur=540,
        partial_allowance=True,
    )

    assert q.allowance_applied is False
    assert q.spread_pct == pytest.approx(0.9)
    assert q.gross_amount == pytest.approx(1000)
    assert q.spread_amount == pytest.approx(4.5)
    assert q.final_amount == pytest.approx(995.5)


def test_r04_swift_fee_includes_required_flat_and_percentage_parts():
    fee = fx.transfer_fee(200, "swift")

    assert fee["flat_fee_eur"] == pytest.approx(15)
    assert fee["percent_fee"] == pytest.approx(0.3)
    assert fee["total_fee_eur"] == pytest.approx(15.6)
