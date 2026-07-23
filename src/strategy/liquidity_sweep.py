"""
Liquidity Sweep / stop-hunt reversal strategy — ICT family.

Concept (from EA repo's ICT/liquidity indicators): price often spikes just beyond
a prior swing high/low to grab stop-loss "liquidity", then sharply reverses. If a
bar takes out a recent extreme but CLOSES back inside, it signals a reversal.

  * Bullish sweep: low pierces the prior N-bar low, but close is back ABOVE it
    (sellers trapped) -> go long.
  * Bearish sweep: high pierces the prior N-bar high, but close is back BELOW it
    (buyers trapped) -> go short.

This is a REVERSAL concept — deliberately different in nature from our trend and
FVG/OB continuation strategies, so it has a chance of adding uncorrelated edge.
Vectorized; no zone state needed.
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy
from .indicators import atr


class LiquiditySweepReversal(Strategy):
    name = "liquidity_sweep_reversal"

    def __init__(
        self,
        lookback: int = 20,
        atr_period: int = 14,
        sl_atr_mult: float = 2.0,
        tp_rr: float = 2.0,
        use_htf_filter: bool = False,   # reversals are often counter-trend
        htf_rule: str = "1D",
        htf_ema_period: int = 50,
    ):
        self.lookback = lookback
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr = tp_rr
        self.use_htf_filter = use_htf_filter
        self.htf_rule = htf_rule
        self.htf_ema_period = htf_ema_period

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["atr"] = atr(out, self.atr_period)

        # Prior N-bar extremes (shift(1) so the current bar is excluded).
        prior_low = out["low"].rolling(self.lookback).min().shift(1)
        prior_high = out["high"].rolling(self.lookback).max().shift(1)

        bull_sweep = (out["low"] < prior_low) & (out["close"] > prior_low)
        bear_sweep = (out["high"] > prior_high) & (out["close"] < prior_high)

        if self.use_htf_filter:
            from .indicators import ema
            htf_close = out["close"].resample(self.htf_rule).last().dropna()
            htf_ema = ema(htf_close, self.htf_ema_period)
            htf_dir = (htf_close > htf_ema).map({True: 1, False: -1}).shift(1)
            hd = htf_dir.reindex(out.index, method="ffill")
            bull_sweep = bull_sweep & (hd == 1)
            bear_sweep = bear_sweep & (hd == -1)

        out["signal"] = 0
        out.loc[bull_sweep.fillna(False), "signal"] = 1
        out.loc[bear_sweep.fillna(False), "signal"] = -1

        warmup = max(self.lookback, self.atr_period)
        out.iloc[:warmup, out.columns.get_loc("signal")] = 0
        return out
