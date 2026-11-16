"""Ручний baseline L11 (крок 1). Пишіть тести тут, асистента не відкривайте.

Модуль під тестом: app/engines/fx.py — функція fx.quote(...).
Очікувані значення беріть із таблиці тарифів app/engines/policy.py,
а не з виводу самої функції.

    fx.quote(amount, from_currency, to_currency, tier, allowance_used_eur=0.0)
    tier: "tier1" | "tier2" | "tier3"
    повертає FxQuote: spread_pct, allowance_applied, gross_amount,
                      spread_amount, final_amount, ...
"""
import pytest

from app.engines import fx

def test_tier2_above_free_limit_has_spread():
    q = fx.quote(1500, "EUR", "USD", "tier2")

    assert q.spread_pct == 0.9

def test_tier1_above_free_limit_has_spread():
    q = fx.quote(600, "EUR", "USD", "tier1")

    assert q.spread_pct == 1.5

def test_tier3_above_free_limit_has_spread():
    q = fx.quote(6000, "EUR", "USD", "tier3")

    assert q.spread_pct == 0.5

def test_tier2_below_free_limit_has_no_spread():
    q = fx.quote(900, "EUR", "USD", "tier2")

    assert q.spread_pct == 0.0

def test_tier1_below_free_limit_has_no_spread():
    q = fx.quote(400, "EUR", "USD", "tier1")

    assert q.spread_pct == 0.0

def test_tier1_final_amount_after_spread():
    q = fx.quote(920, "EUR", "USD", "tier1")

    assert q.gross_amount == pytest.approx(1000)
    assert q.spread_amount == pytest.approx(15)
    assert q.final_amount == pytest.approx(985)

def test_tier1_final_amount_within_free_limit():
    q = fx.quote(300, "EUR", "USD", "tier1")

    assert q.gross_amount == pytest.approx(326.086957)
    assert q.spread_amount == pytest.approx(0)
    assert q.final_amount == pytest.approx(326.086957)