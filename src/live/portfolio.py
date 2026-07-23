"""
The live portfolio: which instrument is traded by which strategy, with FIXED
parameters (live trading needs fixed params, not per-fold re-optimization).

Chosen from the walk-forward research (see docs/RESEARCH_FINDINGS.md):
    * Gold, Silver  -> trend-following (EMA+RSI + daily filter)
    * AUDUSD, USDJPY -> mean-reversion (Bollinger + RSI)

`logical` names map to the broker's REAL symbol names via config/live_config.yaml
(discovered with scripts/check_mt5.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..strategy.base import Strategy
from ..strategy.ema_rsi_swing import EmaRsiSwing
from ..strategy.mean_reversion import BollingerMeanReversion


@dataclass
class PortfolioSlot:
    logical: str                 # e.g. "GOLD"
    timeframe: str               # e.g. "H4"
    strategy_factory: Callable[..., Strategy]
    params: dict
    news_currencies: set[str] = field(default_factory=lambda: {"USD"})
    # Volatility targeting helps mean-reversion (protects it in turbulent
    # regimes) but HURTS trend-following (cuts its skew-driven tail winners),
    # per our walk-forward test. So default ON only for mean-reversion slots.
    use_vol_target: bool = False

    def build(self) -> Strategy:
        return self.strategy_factory(**self.params)


# Fixed, sensible defaults drawn from the parameter ranges that validated OOS.
TREND_PARAMS = dict(
    fast=20, slow=50, sl_atr_mult=2.5, tp_rr=2.0,
    use_htf_filter=True, htf_rule="1D", htf_ema_period=50,
)
MEANREV_PARAMS = dict(
    period=20, num_std=2.0, rsi_oversold=30.0, rsi_overbought=70.0,
    sl_atr_mult=2.5, tp_rr=1.0,
)

DEFAULT_PORTFOLIO: list[PortfolioSlot] = [
    # Trend slots: vol targeting OFF (it cuts their skew-driven tail winners).
    PortfolioSlot("GOLD",   "H4", EmaRsiSwing, dict(TREND_PARAMS), {"USD"}, use_vol_target=False),
    PortfolioSlot("SILVER", "H4", EmaRsiSwing, dict(TREND_PARAMS), {"USD"}, use_vol_target=False),
    # Mean-reversion slots: vol targeting ON (protects them in turbulent regimes;
    # lifted OOS Sharpe ~1.2 -> ~1.5 and cut drawdown in the walk-forward).
    PortfolioSlot("AUDUSD", "H4", BollingerMeanReversion, dict(MEANREV_PARAMS), {"USD", "AUD"}, use_vol_target=True),
    PortfolioSlot("USDJPY", "H4", BollingerMeanReversion, dict(MEANREV_PARAMS), {"USD", "JPY"}, use_vol_target=True),
]
