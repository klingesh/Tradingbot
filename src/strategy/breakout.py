"""
Donchian channel breakout strategy.

Idea (classic trend/momentum breakout):
    * Track the highest high / lowest low of the last N bars.
    * Go long when price breaks ABOVE the prior N-bar high (momentum up).
    * Go short when price breaks BELOW the prior N-bar low (momentum down).
    * ATR-based stops.
    * Optional higher-timeframe trend filter (same anti-look-ahead approach).

Breakout systems tend to work well in trending markets like crypto.
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy
from .indicators import ema, atr


class DonchianBreakout(Strategy):
    name = "donchian_breakout"

    def __init__(
        self,
        channel: int = 20,
        atr_period: int = 14,
        sl_atr_mult: float = 2.5,
        tp_rr: float = 2.0,
        use_htf_filter: bool = False,
        htf_rule: str = "1D",
        htf_ema_period: int = 50,
    ):
        self.channel = channel
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr = tp_rr
        self.use_htf_filter = use_htf_filter
        self.htf_rule = htf_rule
        self.htf_ema_period = htf_ema_period

    def _htf_trend(self, out: pd.DataFrame) -> pd.Series:
        htf_close = out["close"].resample(self.htf_rule).last().dropna()
        htf_ema = ema(htf_close, self.htf_ema_period)
        htf_dir = (htf_close > htf_ema).map({True: 1, False: -1}).shift(1)
        return htf_dir.reindex(out.index, method="ffill")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["atr"] = atr(out, self.atr_period)

        # Prior N-bar channel (shift(1) so the current bar is NOT in its own window).
        upper = out["high"].rolling(self.channel).max().shift(1)
        lower = out["low"].rolling(self.channel).min().shift(1)

        broke_up = (out["close"] > upper) & (out["close"].shift(1) <= upper.shift(1))
        broke_down = (out["close"] < lower) & (out["close"].shift(1) >= lower.shift(1))

        long_entry = broke_up
        short_entry = broke_down

        if self.use_htf_filter:
            out["htf_dir"] = self._htf_trend(out)
            long_entry = long_entry & (out["htf_dir"] == 1)
            short_entry = short_entry & (out["htf_dir"] == -1)

        out["signal"] = 0
        out.loc[long_entry.fillna(False), "signal"] = 1
        out.loc[short_entry.fillna(False), "signal"] = -1

        warmup = max(self.channel, self.atr_period)
        out.iloc[:warmup, out.columns.get_loc("signal")] = 0
        return out
