"""
Event-driven backtest engine.

Rules that keep the test HONEST (no cheating / look-ahead):
  * Signals are decided on a bar's CLOSE (row i).
  * We enter at the NEXT bar's OPEN (row i+1).
  * Stop-loss / take-profit are checked intrabar using each bar's high/low.
  * If both SL and TP could be hit in the same bar, we assume the SL hit first
    (conservative / worst-case).
  * Trading costs (spread + slippage) are applied to every fill.
  * Position size comes from the real risk engine, sized off current equity.

One position at a time (swing style).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..risk.position_sizing import (
    SymbolSpec,
    RiskParams,
    MinLotPolicy,
    calculate_position_size,
)
from ..strategy.base import Strategy
from .metrics import Trade, BacktestReport, build_report


@dataclass
class CostModel:
    """Simple, adverse-fill cost model."""
    spread_frac: float = 0.0004     # half-spread + slippage as fraction of price, per fill
    commission_per_lot: float = 0.0  # account-currency commission per lot, per side


@dataclass
class BacktestConfig:
    initial_balance: float = 100_000.0
    bars_per_year: float = 6 * 365   # H4 -> 6 bars/day
    allow_short: bool = True


def _value_per_point(symbol: SymbolSpec) -> float:
    """Account-currency P&L per 1.0 price unit per 1.0 lot."""
    return symbol.tick_value / symbol.tick_size


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    symbol: SymbolSpec,
    risk: RiskParams,
    cost: CostModel | None = None,
    config: BacktestConfig | None = None,
    trade_start: pd.Timestamp | None = None,
    trade_end: pd.Timestamp | None = None,
) -> tuple[BacktestReport, list[Trade], pd.Series]:
    """
    Run the backtest.

    `trade_start` / `trade_end` (optional) restrict WHERE trades may be opened,
    while indicators are still computed on the FULL `df` (so warm-up/history is
    correct). This is what makes walk-forward out-of-sample testing honest.
    """
    cost = cost or CostModel()
    config = config or BacktestConfig()

    data = strategy.generate_signals(df).reset_index()
    ts_col = data.columns[0]  # 'timestamp'
    vpp = _value_per_point(symbol)

    # Resolve the trading window to integer index bounds (indicators still use all data).
    ts = data[ts_col]
    lo = 1 if trade_start is None else max(1, int((ts < trade_start).sum()))
    hi = len(data) if trade_end is None else int((ts < trade_end).sum())

    balance = config.initial_balance
    equity_points: list[float] = []
    trades: list[Trade] = []

    position = None  # dict when in a trade

    for i in range(lo, hi):
        prev = data.iloc[i - 1]
        bar = data.iloc[i]
        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]

        # ---- Manage an open position (check exits on this bar) ----
        if position is not None:
            side = position["side"]
            exit_price = None
            reason = None

            if side == 1:  # long
                if l <= position["sl"]:
                    exit_price, reason = position["sl"], "sl"
                elif h >= position["tp"]:
                    exit_price, reason = position["tp"], "tp"
            else:  # short
                if h >= position["sl"]:
                    exit_price, reason = position["sl"], "sl"
                elif l <= position["tp"]:
                    exit_price, reason = position["tp"], "tp"

            # Exit on opposite signal (trend flip) at this bar's open.
            if exit_price is None and prev["signal"] == -side:
                exit_price, reason = o, "signal_flip"

            if exit_price is not None:
                fill = _apply_cost(exit_price, -side, cost)  # closing is opposite direction
                pnl = side * (fill - position["entry"]) * vpp * position["lots"]
                pnl -= cost.commission_per_lot * position["lots"]
                balance += pnl
                r_mult = pnl / position["risk_amount"] if position["risk_amount"] else 0.0
                trades.append(
                    Trade(
                        entry_time=position["entry_time"],
                        exit_time=bar[ts_col],
                        side=side,
                        entry=position["entry"],
                        exit=fill,
                        lots=position["lots"],
                        pnl=pnl,
                        r_multiple=r_mult,
                        reason=reason,
                    )
                )
                position = None

        # ---- Consider a new entry (from previous bar's signal) ----
        if position is None and prev["signal"] != 0:
            side = int(prev["signal"])
            if side == -1 and not config.allow_short:
                pass
            else:
                atr_val = prev["atr"]
                if atr_val and atr_val > 0:
                    entry_fill = _apply_cost(o, side, cost)
                    sl_dist = strategy.sl_atr_mult * atr_val
                    sizing = calculate_position_size(
                        balance=balance,
                        stop_loss_distance_price=sl_dist,
                        symbol=symbol,
                        risk=risk,
                    )
                    if sizing.should_trade:
                        if side == 1:
                            sl = entry_fill - sl_dist
                            tp = entry_fill + strategy.tp_rr * sl_dist
                        else:
                            sl = entry_fill + sl_dist
                            tp = entry_fill - strategy.tp_rr * sl_dist
                        position = {
                            "side": side,
                            "entry": entry_fill,
                            "sl": sl,
                            "tp": tp,
                            "lots": sizing.lots,
                            "risk_amount": sizing.projected_risk,
                            "entry_time": bar[ts_col],
                        }

        # ---- Mark-to-market equity for drawdown tracking ----
        if position is not None:
            side = position["side"]
            unreal = side * (c - position["entry"]) * vpp * position["lots"]
            equity_points.append(balance + unreal)
        else:
            equity_points.append(balance)

    equity_curve = pd.Series(equity_points, index=data[ts_col].iloc[lo:hi].values)
    report = build_report(trades, equity_curve, config.initial_balance, config.bars_per_year)
    return report, trades, equity_curve


def _apply_cost(price: float, direction: int, cost: CostModel) -> float:
    """Adverse fill: buys fill a bit higher, sells fill a bit lower."""
    return price * (1 + direction * cost.spread_frac)
