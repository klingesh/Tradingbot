"""
Bollinger-band + RSI mean-reversion strategy.

Idea (counter-trend / range trading):
    * Compute a moving average and standard-deviation bands.
    * Go long when price closes BELOW the lower band and RSI is oversold
      (betting on a bounce back toward the mean).
    * Go short when price closes ABOVE the upper band and RSI is overbought.
    * ATR-based stops.

NOTE: True mean-reversion usually exits at the mean, not at a fixed reward
multiple. Our engine currently uses ATR TP/SL, so we approximate with a small
tp_rr. Expect this archetype to STRUGGLE in strongly trending markets (crypto) --
which is itself a useful research finding, not a bug.
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy
from .indicators import rsi, atr


class BollingerMeanReversion(Strategy):
    name = "bollinger_mean_reversion"

    def __init__(
        self,
        period: int = 20,
        num_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        atr_period: int = 14,
        sl_atr_mult: float = 2.5,
        tp_rr: float = 1.0,   # small target: revert toward the mean
    ):
        self.period = period
        self.num_std = num_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr = tp_rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        mid = out["close"].rolling(self.period).mean()
        std = out["close"].rolling(self.period).std()
        upper = mid + self.num_std * std
        lower = mid - self.num_std * std
        out["rsi"] = rsi(out["close"], self.rsi_period)
        out["atr"] = atr(out, self.atr_period)

        long_entry = (out["close"] < lower) & (out["rsi"] < self.rsi_oversold)
        short_entry = (out["close"] > upper) & (out["rsi"] > self.rsi_overbought)

        out["signal"] = 0
        out.loc[long_entry.fillna(False), "signal"] = 1
        out.loc[short_entry.fillna(False), "signal"] = -1

        warmup = max(self.period, self.atr_period, self.rsi_period)
        out.iloc[:warmup, out.columns.get_loc("signal")] = 0
        return out
