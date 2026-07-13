"""
Does a news avoid-filter improve the recommended portfolio?

For each instrument (with its best-fit strategy), run walk-forward WITHOUT and
WITH a blackout around high-impact USD events (NFP + FOMC), and compare.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from src.data.yahoo_loader import fetch_yahoo_h4, INSTRUMENTS
from src.strategy.ema_rsi_swing import EmaRsiSwing
from src.strategy.mean_reversion import BollingerMeanReversion
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.backtest.engine import CostModel, BacktestConfig
from src.backtest.walk_forward import walk_forward
from src.news.calendar import DeterministicUSCalendar
from src.news.filter import NewsFilter

RESEARCH_SPEC = SymbolSpec(tick_size=1.0, tick_value=1.0,
                           volume_min=1e-6, volume_step=1e-6, volume_max=1e12)
RISK = RiskParams(risk_percent_per_trade=2.0, max_risk_percent_per_trade=5.0,
                  on_min_lot_exceeds_risk=MinLotPolicy.MIN)
CONFIG = BacktestConfig(initial_balance=100_000.0, bars_per_year=5 * 252, allow_short=True)
COST = CostModel(spread_frac=0.0004)

TREND_GRID = {"fast": [10, 20], "slow": [50, 100], "sl_atr_mult": [2.0, 2.5, 3.0],
              "tp_rr": [1.5, 2.0, 3.0], "use_htf_filter": [True], "htf_rule": ["1D"],
              "htf_ema_period": [50]}
MEANREV_GRID = {"period": [20, 30], "num_std": [2.0, 2.5], "rsi_oversold": [25.0, 30.0],
                "rsi_overbought": [70.0, 75.0], "sl_atr_mult": [2.0, 3.0], "tp_rr": [1.0, 1.5]}

# instrument -> (strategy factory, grid)
PORTFOLIO = {
    "XAUUSD": (EmaRsiSwing, TREND_GRID),
    "XAGUSD": (EmaRsiSwing, TREND_GRID),
    "AUDUSD": (BollingerMeanReversion, MEANREV_GRID),
    "USDJPY": (BollingerMeanReversion, MEANREV_GRID),
}


def run(df, factory, grid, blackout):
    return walk_forward(df, factory, grid, RESEARCH_SPEC, RISK, COST, CONFIG,
                        is_bars=1000, oos_bars=350, step_bars=350, min_trades_is=10,
                        blackout=blackout).oos_report


def main() -> None:
    cal = DeterministicUSCalendar()
    print("News avoid-filter: blackout +/-120min around NFP & FOMC (USD).\n")
    print(f"{'Inst':<7} {'Filter':<8} {'Trades':>6} {'Win':>6} {'PF':>5} {'Exp(R)':>8} "
          f"{'Return':>9} {'MaxDD':>7} {'Sharpe':>6}")
    print("-" * 70)

    for name, (factory, grid) in PORTFOLIO.items():
        ysym = INSTRUMENTS[name][0]
        df = fetch_yahoo_h4(ysym)
        events = cal.events(df.index[0], df.index[-1])
        nf = NewsFilter(events, before_minutes=120, after_minutes=120, currencies={"USD"})
        mask = nf.blackout_mask(df.index, bar_minutes=240)

        base = run(df, factory, grid, None)
        filt = run(df, factory, grid, mask)
        blk_pct = mask.mean() * 100
        for tag, r in (("OFF", base), ("ON", filt)):
            print(f"{name:<7} {tag:<8} {r.num_trades:>6} {r.win_rate:>5.1f}% {r.profit_factor:>5.2f} "
                  f"{r.expectancy_r:>+8.3f} {r.total_return_pct:>+8.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe:>6.2f}")
        print(f"        (blackout covered {blk_pct:.1f}% of bars)\n")


if __name__ == "__main__":
    main()
