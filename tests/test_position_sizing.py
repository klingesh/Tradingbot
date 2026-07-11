"""Tests for the position sizing / risk engine."""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.risk.position_sizing import (  # noqa: E402
    SymbolSpec,
    RiskParams,
    MinLotPolicy,
    calculate_position_size,
)


# A representative crypto CFD spec (illustrative values; real ones come from MT5).
# tick_size=0.01 price move, tick_value = account-currency value per tick per 1.0 lot.
BTC_SPEC = SymbolSpec(
    tick_size=0.01,
    tick_value=0.01,     # -> 1.0 price move = 1.0 currency unit per 1.0 lot
    volume_min=0.01,
    volume_step=0.01,
    volume_max=100.0,
)


def test_basic_sizing_standard_account():
    # Balance 10,000 (dollars). Risk 2% = 200. SL distance 1000 price units.
    # money_risk_per_lot = (1000 / 0.01) * 0.01 = 1000. raw_lots = 200/1000 = 0.2
    result = calculate_position_size(
        balance=10_000,
        stop_loss_distance_price=1000.0,
        symbol=BTC_SPEC,
        risk=RiskParams(risk_percent_per_trade=2.0),
    )
    assert result.should_trade
    assert result.lots == pytest.approx(0.20)
    assert result.projected_risk == pytest.approx(200.0)
    assert result.projected_risk_percent == pytest.approx(2.0)


def test_cent_account_currency_agnostic():
    # Cent account: $100 deposit shows as 10,000 (cents). tick_value also in cents.
    # Same numbers, correct answer -> proves currency-agnostic design.
    result = calculate_position_size(
        balance=10_000,   # cents
        stop_loss_distance_price=1000.0,
        symbol=BTC_SPEC,
        risk=RiskParams(risk_percent_per_trade=2.0),
    )
    assert result.projected_risk_percent == pytest.approx(2.0)


def test_risk_cap_is_enforced():
    # Ask for 20% but cap is 5% -> effective risk must be 5%.
    result = calculate_position_size(
        balance=10_000,
        stop_loss_distance_price=1000.0,
        symbol=BTC_SPEC,
        risk=RiskParams(risk_percent_per_trade=20.0, max_risk_percent_per_trade=5.0),
    )
    assert result.projected_risk_percent <= 5.0 + 1e-9


def test_lots_rounded_down_never_over_risk():
    # Choose numbers that don't divide evenly; rounding must go DOWN.
    result = calculate_position_size(
        balance=3_333,
        stop_loss_distance_price=777.0,
        symbol=BTC_SPEC,
        risk=RiskParams(risk_percent_per_trade=2.0),
    )
    # projected risk must never exceed the intended risk amount
    assert result.projected_risk <= result.risk_amount + 1e-9
    # lot must be a clean multiple of the step
    assert math.isclose(result.lots % BTC_SPEC.volume_step, 0.0, abs_tol=1e-8) or \
           math.isclose(result.lots % BTC_SPEC.volume_step, BTC_SPEC.volume_step, abs_tol=1e-8)


def test_skip_when_min_lot_too_risky():
    # Tiny balance: even 0.01 lot risks more than 2%. Policy SKIP -> no trade.
    result = calculate_position_size(
        balance=100,   # very small
        stop_loss_distance_price=1000.0,
        symbol=BTC_SPEC,
        risk=RiskParams(
            risk_percent_per_trade=2.0,
            on_min_lot_exceeds_risk=MinLotPolicy.SKIP,
        ),
    )
    assert not result.should_trade
    assert result.lots == 0.0
    assert "Skipped" in result.reason


def test_min_policy_takes_min_lot():
    # Same tiny balance, but policy MIN -> take the minimum lot anyway.
    result = calculate_position_size(
        balance=100,
        stop_loss_distance_price=1000.0,
        symbol=BTC_SPEC,
        risk=RiskParams(
            risk_percent_per_trade=2.0,
            on_min_lot_exceeds_risk=MinLotPolicy.MIN,
        ),
    )
    assert result.should_trade
    assert result.lots == BTC_SPEC.volume_min


def test_zero_stop_distance_is_rejected():
    result = calculate_position_size(
        balance=10_000,
        stop_loss_distance_price=0.0,
        symbol=BTC_SPEC,
        risk=RiskParams(risk_percent_per_trade=2.0),
    )
    assert not result.should_trade


def test_invalid_symbol_spec_raises():
    with pytest.raises(ValueError):
        SymbolSpec(tick_size=0, tick_value=1, volume_min=0.01, volume_step=0.01, volume_max=1)
