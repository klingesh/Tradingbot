"""
Walk-forward test of MEAN-REVERSION (Bollinger + RSI) on the range-bound forex
majors at H4. Trend-following failed on these (they whipsaw); the hypothesis is
that fading extremes back toward the mean suits them better.

Compared head-to-head with the trend strategy's H4 numbers.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.yahoo_loader import fetch_yahoo_h4, INSTRUMENTS
from src.strategy.mean_reversion import BollingerMeanReversion
from src.strategy.ema_rsi_swing import EmaRsiSwing
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.backtest.engine import CostModel, BacktestConfig
from src.backtest.walk_forward import walk_forward

RESEARCH_SPEC = SymbolSpec(tick_size=1.0, tick_value=1.0,
                           volume_min=1e-6, volume_step=1e-6, volume_max=1e12)
RISK = RiskParams(risk_percent_per_trade=2.0, max_risk_percent_per_trade=5.0,
                  on_min_lot_exceeds_risk=MinLotPolicy.MIN)
CONFIG = BacktestConfig(initial_balance=100_000.0, bars_per_year=5 * 252, allow_short=True)
COST = CostModel(spread_frac=0.0001)  # forex majors, tight

MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]

MEANREV_GRID = {
    "period": [20, 30],
    "num_std": [2.0, 2.5],
    "rsi_oversold": [25.0, 30.0],
    "rsi_overbought": [70.0, 75.0],
    "sl_atr_mult": [2.0, 3.0],
    "tp_rr": [1.0, 1.5],
}
TREND_GRID = {
    "fast": [10, 20], "slow": [50, 100],
    "sl_atr_mult": [2.0, 2.5, 3.0], "tp_rr": [1.5, 2.0, 3.0],
    "use_htf_filter": [True], "htf_rule": ["1D"], "htf_ema_period": [50],
}


def wf(df, factory, grid):
    return walk_forward(df, factory, grid, RESEARCH_SPEC, RISK, COST, CONFIG,
                        is_bars=1000, oos_bars=350, step_bars=350, min_trades_is=10).oos_report


def line(name, tag, r):
    return (f"{name:<8} {tag:<12} {r.num_trades:>6} {r.win_rate:>5.1f}% {r.profit_factor:>5.2f} "
            f"{r.expectancy_r:>+8.3f} {r.total_return_pct:>+8.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe:>6.2f}")


def main() -> None:
    print(f"{'Pair':<8} {'Strategy':<12} {'Trades':>6} {'Win':>6} {'PF':>5} "
          f"{'Exp(R)':>8} {'Return':>9} {'MaxDD':>7} {'Sharpe':>6}")
    print("-" * 78)
    mr_sum = tr_sum = 0.0
    for name in MAJORS:
        ysym = INSTRUMENTS[name][0]
        df = fetch_yahoo_h4(ysym)
        tr = wf(df, EmaRsiSwing, TREND_GRID)
        mr = wf(df, BollingerMeanReversion, MEANREV_GRID)
        print(line(name, "trend", tr))
        print(line(name, "mean-revert", mr))
        print()
        tr_sum += tr.total_return_pct
        mr_sum += mr.total_return_pct
    print("-" * 78)
    print(f"Avg OOS return  ->  trend: {tr_sum/len(MAJORS):+.2f}%   "
          f"mean-reversion: {mr_sum/len(MAJORS):+.2f}%")


if __name__ == "__main__":
    main()
