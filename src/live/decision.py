"""
Pure trading-decision logic (no MT5, no I/O) - so it is fully unit-testable.

Given the latest signals, current position, live prices and account state, it
returns ONE decision: enter / close / hold / skip / nothing. The orchestrator
executes it. This mirrors the backtest engine's rules so live behaviour matches
what we validated.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..risk.position_sizing import SymbolSpec, RiskParams, calculate_position_size


@dataclass
class Decision:
    action: str          # "enter" | "close" | "hold" | "skip" | "nothing"
    side: int = 0        # +1 long / -1 short (for "enter")
    lots: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    reason: str = ""


def decide(
    signals: pd.DataFrame,
    position_side: int,          # current position: +1, -1, or 0 if flat
    bid: float,
    ask: float,
    balance: float,
    spec: SymbolSpec,
    risk: RiskParams,
    sl_atr_mult: float,
    tp_rr: float,
    blackout: bool = False,
) -> Decision:
    """
    Decide the action for one instrument based on its most recent CLOSED bar.

    Uses the last row of `signals` (which must already be a closed bar - the
    caller drops the still-forming bar). No look-ahead: we act on completed data.
    """
    if len(signals) == 0:
        return Decision("nothing", reason="no data")

    last = signals.iloc[-1]
    sig = int(last.get("signal", 0))
    atr = float(last.get("atr", 0.0))

    # ---- Manage an existing position ----
    if position_side != 0:
        # Close on a fresh opposite signal (trend flip), matching the backtester.
        if sig == -position_side:
            return Decision("close", side=position_side, reason="opposite signal (flip)")
        return Decision("hold", side=position_side, reason="position open, no exit signal")

    # ---- Consider a new entry ----
    if sig == 0:
        return Decision("nothing", reason="no entry signal")
    if blackout:
        return Decision("skip", side=sig, reason="news blackout window")
    if atr <= 0:
        return Decision("skip", side=sig, reason="invalid ATR")

    side = sig
    entry = ask if side == 1 else bid
    sl_dist = sl_atr_mult * atr

    sizing = calculate_position_size(
        balance=balance,
        stop_loss_distance_price=sl_dist,
        symbol=spec,
        risk=risk,
    )
    if not sizing.should_trade:
        return Decision("skip", side=side, reason=f"sizing: {sizing.reason}")

    if side == 1:
        sl = entry - sl_dist
        tp = entry + tp_rr * sl_dist
    else:
        sl = entry + sl_dist
        tp = entry - tp_rr * sl_dist

    return Decision(
        "enter", side=side, lots=sizing.lots, sl=sl, tp=tp,
        reason=f"entry {'LONG' if side == 1 else 'SHORT'}; {sizing.reason}",
    )
