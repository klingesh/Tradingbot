"""
Does the volatility-targeting overlay improve the validated portfolio?

For each instrument (with its best-fit strategy) we run the walk-forward WITHOUT
and WITH the vol-target scalar and compare risk-adjusted results. Vol-target
params are FIXED (not grid-searched) to avoid overfitting the overlay itself.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.loader import fetch_okx_ohlcv
from src.data.yahoo_loader import fetch_yahoo_h4, INSTRUMENTS
from src.strategy.ema_rsi_swing import EmaRsiSwing
from src.strategy.mean_reversion import BollingerMeanReversion
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.risk.vol_target import volatility_target_scalar
from src.backtest.engine import CostModel, BacktestConfig
from src.backtest.walk_forward import walk_forward

SPEC = SymbolSpec(tick_size=1.0, tick_value=1.0, volume_min=1e-6, volume_step=1e-6, volume_max=1e12)
RISK = RiskParams(2.0, 5.0, MinLotPolicy.MIN)

TREND = {"fast": [10, 20], "slow": [50, 100], "sl_atr_mult": [2.0, 2.5, 3.0],
         "tp_rr": [1.5, 2.0, 3.0], "use_htf_filter": [True], "htf_rule": ["1D"],
         "htf_ema_period": [50]}
MEANREV = {"period": [20, 30], "num_std": [2.0, 2.5], "rsi_oversold": [25.0, 30.0],
           "rsi_overbought": [70.0, 75.0], "sl_atr_mult": [2.0, 3.0], "tp_rr": [1.0, 1.5]}

# name, factory, grid, source, bars/yr, is, oos, step, spread
PORT = [
    ("BTC",    EmaRsiSwing,             TREND,   "okx", 6 * 365, 1500, 500, 500, 0.0004),
    ("XAUUSD", EmaRsiSwing,             TREND,   "yh",  5 * 252, 1000, 350, 350, 0.0004),
    ("XAGUSD", EmaRsiSwing,             TREND,   "yh",  5 * 252, 1000, 350, 350, 0.0004),
    ("AUDUSD", BollingerMeanReversion,  MEANREV, "yh",  5 * 252, 1000, 350, 350, 0.0001),
    ("USDJPY", BollingerMeanReversion,  MEANREV, "yh",  5 * 252, 1000, 350, 350, 0.0001),
]


def load(name, source):
    return fetch_okx_ohlcv("BTC-USDT", "H4", 6000) if source == "okx" \
        else fetch_yahoo_h4(INSTRUMENTS[name][0])


def main() -> None:
    print(f"{'Instrument':<9} {'VolTgt':<7} {'Trades':>6} {'PF':>5} {'Exp(R)':>7} "
          f"{'Return':>8} {'MaxDD':>7} {'Sharpe':>6}")
    print("-" * 62)
    agg = {"off": [0.0, 0.0, 0], "on": [0.0, 0.0, 0]}  # [sharpe_sum, ret_sum, n]

    for name, factory, grid, src, bpy, isb, oosb, step, spread in PORT:
        df = load(name, src)
        vs = volatility_target_scalar(df["close"], lookback=14, median_window=500,
                                      min_scale=0.5, max_scale=1.5)
        cfg = BacktestConfig(initial_balance=100_000.0, bars_per_year=bpy, allow_short=True)
        cost = CostModel(spread_frac=spread)
        for tag, scalar in (("off", None), ("on", vs)):
            r = walk_forward(df, factory, grid, SPEC, RISK, cost, cfg,
                             is_bars=isb, oos_bars=oosb, step_bars=step,
                             min_trades_is=10, vol_scalar=scalar).oos_report
            print(f"{name:<9} {tag:<7} {r.num_trades:>6} {r.profit_factor:>5.2f} "
                  f"{r.expectancy_r:>+7.3f} {r.total_return_pct:>+7.2f}% "
                  f"{r.max_drawdown_pct:>6.2f}% {r.sharpe:>6.2f}")
            agg[tag][0] += r.sharpe
            agg[tag][1] += r.total_return_pct
            agg[tag][2] += 1
        print()

    for tag in ("off", "on"):
        s, ret, n = agg[tag]
        print(f"AVG vol-target {tag.upper():<3}: Sharpe {s/n:.2f}   Return {ret/n:+.2f}%")


if __name__ == "__main__":
    main()
