"""Strategy base class.

A strategy's only job is to look at (closed) candles and emit an intent:
    +1 = want to be long
    -1 = want to be short
     0 = no position wanted

It also exposes ATR-based stop parameters. The backtest/execution engine is
responsible for entries, exits, position sizing and risk - NOT the strategy.
This separation keeps strategies simple and swappable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name: str = "base"

    # ATR-based risk geometry (engine reads these).
    sl_atr_mult: float = 2.0   # stop-loss = entry -/+ sl_atr_mult * ATR
    tp_rr: float = 2.0         # take-profit distance = tp_rr * (stop distance)
    atr_period: int = 14

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return a copy of df with (at least) these added columns:
            signal : int   (+1 long / -1 short / 0 flat) decided on THAT bar's close
            atr    : float (volatility used for stop sizing)

        Must be free of look-ahead bias: row i may only use data up to row i.
        """
        raise NotImplementedError
