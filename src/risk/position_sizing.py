"""
Position sizing / risk engine.

This is the survival layer of the bot. Given how much of the account we are
willing to risk and where the stop-loss sits, it computes the correct MetaTrader 5
lot size and enforces hard safety caps.

Design principle: currency-agnostic.
    We never hardcode "dollars" or "cents". We use whatever `balance` and
    `tick_value` MetaTrader 5 reports for the account. On a JustMarkets CENT
    account these are in cents; on a standard account they're in dollars.
    Because both come from the same account, the math stays correct either way.

The key formula
---------------
    risk_amount           = balance * (risk_percent / 100)
    ticks_to_stop         = stop_loss_distance_price / tick_size
    money_risk_per_lot    = ticks_to_stop * tick_value
    raw_lots              = risk_amount / money_risk_per_lot
    lots                  = clamp_and_round(raw_lots)   # to broker's volume rules

`tick_size`  = smallest price increment for the symbol   (mt5.symbol_info().trade_tick_size)
`tick_value` = account-currency value of one tick per 1.0 lot (mt5.symbol_info().trade_tick_value)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class MinLotPolicy(str, Enum):
    """What to do when even the broker's minimum lot risks more than allowed."""
    SKIP = "skip"   # do not take the trade (recommended)
    MIN = "min"     # take the minimum lot anyway (accepts higher risk)


@dataclass(frozen=True)
class SymbolSpec:
    """
    Broker/symbol trading rules. In production these come straight from
    mt5.symbol_info() for the given symbol.
    """
    tick_size: float      # trade_tick_size  (smallest price move)
    tick_value: float     # trade_tick_value (account-currency value per tick per 1.0 lot)
    volume_min: float     # minimum lot size (e.g. 0.01)
    volume_step: float    # lot increment    (e.g. 0.01)
    volume_max: float     # maximum lot size

    def __post_init__(self) -> None:
        for field_name in ("tick_size", "tick_value", "volume_min", "volume_step", "volume_max"):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"SymbolSpec.{field_name} must be > 0")
        if self.volume_max < self.volume_min:
            raise ValueError("volume_max must be >= volume_min")


@dataclass(frozen=True)
class RiskParams:
    """Risk configuration (mirrors config.yaml -> risk)."""
    risk_percent_per_trade: float
    max_risk_percent_per_trade: float = 5.0
    on_min_lot_exceeds_risk: MinLotPolicy = MinLotPolicy.SKIP


@dataclass(frozen=True)
class SizingResult:
    """Outcome of a sizing calculation."""
    lots: float                 # lot size to trade (0.0 means "do not trade")
    risk_amount: float          # account-currency amount we intended to risk
    projected_risk: float       # actual account-currency risk at the chosen lot size
    projected_risk_percent: float
    reason: str                 # human-readable explanation

    @property
    def should_trade(self) -> bool:
        return self.lots > 0.0


def _round_down_to_step(value: float, step: float) -> float:
    """Round a volume DOWN to the nearest valid step (never round risk up)."""
    steps = math.floor(round(value / step, 8))
    return round(steps * step, 8)


def calculate_position_size(
    balance: float,
    stop_loss_distance_price: float,
    symbol: SymbolSpec,
    risk: RiskParams,
) -> SizingResult:
    """
    Compute the lot size to trade for a single position.

    Parameters
    ----------
    balance
        Current account balance in the account's currency (cents on a cent account).
    stop_loss_distance_price
        Distance between entry and stop-loss, expressed in PRICE units
        (e.g. for BTCUSD entry 60000 with SL 59000 -> 1000.0).
    symbol
        Broker trading rules for the instrument.
    risk
        Risk configuration.

    Returns
    -------
    SizingResult
        `lots == 0.0` means the trade should be skipped.
    """
    if balance <= 0:
        return SizingResult(0.0, 0.0, 0.0, 0.0, "Balance is zero or negative.")
    if stop_loss_distance_price <= 0:
        return SizingResult(0.0, 0.0, 0.0, 0.0, "Stop-loss distance must be > 0.")

    # 1) Clamp requested risk % to the hard cap.
    effective_risk_pct = min(risk.risk_percent_per_trade, risk.max_risk_percent_per_trade)
    risk_amount = balance * (effective_risk_pct / 100.0)

    # 2) Money risked per 1.0 lot given this stop distance.
    ticks_to_stop = stop_loss_distance_price / symbol.tick_size
    money_risk_per_lot = ticks_to_stop * symbol.tick_value
    if money_risk_per_lot <= 0:
        return SizingResult(0.0, risk_amount, 0.0, 0.0, "Invalid tick math (risk per lot <= 0).")

    # 3) Raw lots, then snap to the broker's volume step (rounding DOWN).
    raw_lots = risk_amount / money_risk_per_lot
    lots = _round_down_to_step(raw_lots, symbol.volume_step)

    # 4) Enforce min/max volume rules.
    if lots < symbol.volume_min:
        # Even the smallest lot risks more than we wanted.
        min_lot_risk = symbol.volume_min * money_risk_per_lot
        min_lot_risk_pct = min_lot_risk / balance * 100.0
        if risk.on_min_lot_exceeds_risk is MinLotPolicy.SKIP:
            return SizingResult(
                0.0, risk_amount, 0.0, 0.0,
                f"Skipped: min lot {symbol.volume_min} risks {min_lot_risk_pct:.2f}% "
                f"(> target {effective_risk_pct:.2f}%). Widen account or tighten stop.",
            )
        lots = symbol.volume_min  # MinLotPolicy.MIN

    if lots > symbol.volume_max:
        lots = symbol.volume_max

    # 5) Report the ACTUAL risk at the chosen lot size (may differ due to rounding).
    projected_risk = lots * money_risk_per_lot
    projected_risk_percent = projected_risk / balance * 100.0

    return SizingResult(
        lots=lots,
        risk_amount=risk_amount,
        projected_risk=projected_risk,
        projected_risk_percent=projected_risk_percent,
        reason=(
            f"Risk {effective_risk_pct:.2f}% of {balance:.2f} = {risk_amount:.2f}; "
            f"lot={lots} risks {projected_risk:.2f} ({projected_risk_percent:.2f}%)."
        ),
    )
