"""
Volatility targeting overlay.

Evidence-backed enhancement (Moreira & Muir "Volatility-Managed Portfolios";
vol-scaled momentum studies): scale risk DOWN when volatility is elevated and UP
when calm, to stabilise realised risk. It consistently improves Sharpe and cuts
drawdowns because high volatility predicts more high volatility but NOT
proportionally higher returns.

Our per-trade sizing already normalises for volatility via ATR-based stops (wider
stop in high vol -> smaller position). This overlay adds the missing *regime*
piece: a scalar on the risk fraction based on how current volatility compares to
its own recent norm.

    realized_vol_t = stdev(log returns) over `lookback`
    target_t       = trailing median of realized_vol   (self-calibrating, no
                     fixed magic target, instrument-agnostic)
    scalar_t       = clamp(target_t / realized_vol_t, min_scale, max_scale)

The scalar is SHIFTED by one bar so an entry only ever uses volatility info from
already-closed bars (no look-ahead).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def volatility_target_scalar(
    close: pd.Series,
    lookback: int = 20,
    median_window: int = 252,
    min_scale: float = 0.5,
    max_scale: float = 1.5,
) -> np.ndarray:
    """
    Return a per-bar risk scalar aligned to `close`'s index. `scalar[i]` is safe
    to use for an entry at bar i (it is computed only from data up to bar i-1).

    Defaults to 1.0 during warm-up (behaves like plain fixed-fractional risk).
    """
    ret = np.log(close / close.shift(1))
    rvol = ret.rolling(lookback).std()
    target = rvol.rolling(median_window, min_periods=lookback).median()

    scalar = (target / rvol).clip(lower=min_scale, upper=max_scale)
    # Shift by one bar so bar i uses volatility measured through bar i-1.
    scalar = scalar.shift(1).fillna(1.0)
    return scalar.to_numpy(dtype=float)
