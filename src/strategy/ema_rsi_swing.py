"""
EMA + RSI trend-following swing strategy.

Idea (classic, robust trend-following):
    * Trend direction from a fast/slow EMA relationship.
    * Momentum confirmation from RSI (don't fight momentum).
    * Enter on a fresh EMA crossover in the trend direction.
    * ATR-based stops so risk adapts to volatility.

This is a STARTING POINT to validate the pipeline, not a holy grail. We iterate
on it using backtest expectancy, not gut feeling.
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy
from .indicators import ema, rsi, atr


class EmaRsiSwing(Strategy):
    name = "ema_rsi_swing"

    def __init__(
        self,
        fast: int = 20,
        slow: int = 50,
        rsi_period: int = 14,
        rsi_long_min: float = 50.0,
        rsi_short_max: float = 50.0,
        atr_period: int = 14,
        sl_atr_mult: float = 2.5,
        tp_rr: float = 2.0,
    ):
        self.fast = fast
        self.slow = slow
        self.rsi_period = rsi_period
        self.rsi_long_min = rsi_long_min
        self.rsi_short_max = rsi_short_max
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr = tp_rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["ema_fast"] = ema(out["close"], self.fast)
        out["ema_slow"] = ema(out["close"], self.slow)
        out["rsi"] = rsi(out["close"], self.rsi_period)
        out["atr"] = atr(out, self.atr_period)

        fast_above = out["ema_fast"] > out["ema_slow"]
        # Fresh crossover this bar (compared to previous bar).
        cross_up = fast_above & ~fast_above.shift(1, fill_value=False)
        cross_down = ~fast_above & fast_above.shift(1, fill_value=False)

        long_entry = cross_up & (out["rsi"] > self.rsi_long_min)
        short_entry = cross_down & (out["rsi"] < self.rsi_short_max)

        out["signal"] = 0
        out.loc[long_entry, "signal"] = 1
        out.loc[short_entry, "signal"] = -1

        # Warm-up period has unreliable indicators -> force flat.
        warmup = max(self.slow, self.atr_period, self.rsi_period)
        out.iloc[:warmup, out.columns.get_loc("signal")] = 0
        return out
