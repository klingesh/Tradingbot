"""
Order Block (OB) continuation strategy — SMC / Supply-Demand family.

Concept (from EA repo, e.g. Indi 4 "Order Blocks ... + OB Retest"):
an order block is the last opposite-colour candle before an impulsive move that
breaks structure. That candle's range becomes a demand (bullish OB) or supply
(bearish OB) zone. When price later RETESTS the zone in the trend direction, we
enter, expecting continuation.

  * Bullish OB: last bearish candle before a strong up-move -> demand zone
    [low, high] of that bearish candle.
  * Bearish OB: last bullish candle before a strong down-move -> supply zone.

Rules (no look-ahead, one-shot mitigation, ATR stops, optional HTF trend filter)
mirror the FVG strategy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy
from .indicators import ema, atr


class OrderBlockContinuation(Strategy):
    name = "order_block_continuation"

    def __init__(
        self,
        atr_period: int = 14,
        sl_atr_mult: float = 2.5,
        tp_rr: float = 2.0,
        impulse_atr: float = 1.0,       # move must be >= this * ATR to qualify OB
        max_zone_age: int = 50,
        use_htf_filter: bool = True,
        htf_rule: str = "1D",
        htf_ema_period: int = 50,
    ):
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr = tp_rr
        self.impulse_atr = impulse_atr
        self.max_zone_age = max_zone_age
        self.use_htf_filter = use_htf_filter
        self.htf_rule = htf_rule
        self.htf_ema_period = htf_ema_period

    def _htf_dir(self, out: pd.DataFrame) -> np.ndarray:
        htf_close = out["close"].resample(self.htf_rule).last().dropna()
        htf_ema = ema(htf_close, self.htf_ema_period)
        d = (htf_close > htf_ema).map({True: 1, False: -1}).shift(1)
        return d.reindex(out.index, method="ffill").to_numpy(dtype=float)

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["atr"] = atr(out, self.atr_period)

        o = out["open"].to_numpy(dtype=float)
        high = out["high"].to_numpy(dtype=float)
        low = out["low"].to_numpy(dtype=float)
        close = out["close"].to_numpy(dtype=float)
        atr_arr = out["atr"].to_numpy(dtype=float)
        n = len(out)

        use_htf = self.use_htf_filter
        htf = self._htf_dir(out) if use_htf else None

        signal = np.zeros(n, dtype=int)
        bull_zones: list[tuple[float, float, int]] = []
        bear_zones: list[tuple[float, float, int]] = []
        age = self.max_zone_age
        impulse = self.impulse_atr

        for i in range(2, n):
            hi, lo, cl = high[i], low[i], close[i]
            fired = 0

            # Bullish OB zones (demand): enter long on retrace down into zone.
            kept = []
            for (bot, top, cj) in bull_zones:
                if cl < bot:
                    continue
                if i - cj > age:
                    continue
                if fired == 0 and cj < i and lo <= top:
                    if not use_htf or htf[i] == 1:
                        fired = 1
                    continue
                kept.append((bot, top, cj))
            bull_zones = kept

            # Bearish OB zones (supply): enter short on retrace up into zone.
            kept_b = []
            for (bot, top, cj) in bear_zones:
                if cl > top:
                    continue
                if i - cj > age:
                    continue
                if fired == 0 and cj < i and hi >= bot:
                    if not use_htf or htf[i] == -1:
                        fired = -1
                    continue
                kept_b.append((bot, top, cj))
            bear_zones = kept_b

            # Detect a NEW order block at bar i: prev candle opposite colour,
            # current candle an impulsive break.
            a = atr_arr[i]
            if not np.isnan(a) and a > 0:
                prev_bear = close[i - 1] < o[i - 1]
                prev_bull = close[i - 1] > o[i - 1]
                move = cl - o[i]
                if prev_bear and cl > high[i - 1] and move >= impulse * a:
                    # bullish OB = the prior bearish candle's range
                    bull_zones.append((low[i - 1], high[i - 1], i))
                elif prev_bull and cl < low[i - 1] and (-move) >= impulse * a:
                    bear_zones.append((low[i - 1], high[i - 1], i))

            signal[i] = fired

        out["signal"] = signal
        warmup = max(self.atr_period, 3)
        out.iloc[:warmup, out.columns.get_loc("signal")] = 0
        return out
