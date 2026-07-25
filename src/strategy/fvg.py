"""
Fair Value Gap (FVG) pullback-continuation strategy.

Concept mined from the EA repo's Smart Money Concepts indicators (see EA/Indi 39,
92). A Fair Value Gap is a 3-candle price imbalance:

    * Bullish FVG (BISI): low[0] > high[2]   -> gap zone = [high[2], low[0]]  (support)
    * Bearish FVG (SIBI): high[0] < low[2]   -> gap zone = [high[0], low[2]]  (resistance)

Trading idea (continuation): a fresh FVG is an untraded imbalance that tends to
act as support/resistance. When price RETRACES back into a bullish FVG (a
demand zone) while the higher-timeframe trend is up, we go long, expecting the
move to continue. Mirror for shorts.

Rules that keep it honest:
  * FVG is detected on CLOSED bars (i-2, i-1, i); signal emitted at bar i close;
    the engine enters at the next bar's open (no look-ahead).
  * A zone can only trigger on a bar AFTER it formed, and only once (mitigated).
  * A zone is invalidated if price closes through it, or after `max_zone_age` bars.
  * Optional HTF trend filter (same anti-look-ahead shift as our other strategies).
  * Optional minimum gap size (in ATR) to skip insignificant micro-gaps.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy
from .indicators import ema, atr


class FvgContinuation(Strategy):
    name = "fvg_continuation"

    def __init__(
        self,
        atr_period: int = 14,
        sl_atr_mult: float = 2.5,
        tp_rr: float = 2.0,
        max_zone_age: int = 50,
        min_gap_atr: float = 0.0,       # require gap >= this * ATR (0 = off)
        use_htf_filter: bool = True,
        htf_rule: str = "1D",
        htf_ema_period: int = 50,
    ):
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr = tp_rr
        self.max_zone_age = max_zone_age
        self.min_gap_atr = min_gap_atr
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

        high = out["high"].to_numpy(dtype=float)
        low = out["low"].to_numpy(dtype=float)
        close = out["close"].to_numpy(dtype=float)
        atr_arr = out["atr"].to_numpy(dtype=float)
        n = len(out)

        use_htf = self.use_htf_filter
        htf = self._htf_dir(out) if use_htf else None

        signal = np.zeros(n, dtype=int)
        bull_zones: list[tuple[float, float, int]] = []  # (bottom, top, created_i)
        bear_zones: list[tuple[float, float, int]] = []
        age = self.max_zone_age
        min_gap = self.min_gap_atr

        for i in range(2, n):
            hi, lo, cl = high[i], low[i], close[i]
            fired = 0

            # --- 1) Bullish zones: price retraces DOWN into a demand gap ---
            kept = []
            for (bot, top, cj) in bull_zones:
                if cl < bot:                       # closed below -> gap broken
                    continue
                if i - cj > age:                   # expired
                    continue
                if fired == 0 and cj < i and lo <= top:   # retraced into zone
                    if not use_htf or htf[i] == 1:
                        fired = 1
                    continue                        # mitigated (consume)
                kept.append((bot, top, cj))
            bull_zones = kept

            # --- 2) Bearish zones: price retraces UP into a supply gap ---
            kept_b = []
            for (bot, top, cj) in bear_zones:
                if cl > top:                       # closed above -> gap broken
                    continue
                if i - cj > age:
                    continue
                if fired == 0 and cj < i and hi >= bot:
                    if not use_htf or htf[i] == -1:
                        fired = -1
                    continue
                kept_b.append((bot, top, cj))
            bear_zones = kept_b

            # --- 3) Detect a NEW FVG at bar i (candles i-2, i-1, i) ---
            a = atr_arr[i]
            gap_ok = (not np.isnan(a)) and a > 0
            if low[i] > high[i - 2]:               # bullish FVG
                bottom, top = high[i - 2], low[i]
                if gap_ok and (top - bottom) >= min_gap * a:
                    bull_zones.append((bottom, top, i))
            elif high[i] < low[i - 2]:             # bearish FVG
                bottom, top = high[i], low[i - 2]
                if gap_ok and (top - bottom) >= min_gap * a:
                    bear_zones.append((bottom, top, i))

            signal[i] = fired

        out["signal"] = signal
        warmup = max(self.atr_period, 3)
        out.iloc[:warmup, out.columns.get_loc("signal")] = 0
        return out
