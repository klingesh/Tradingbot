"""
Universe scan: walk-forward test trend-following AND mean-reversion across the
full expanded universe (forex, commodities, indices, crypto). For each
instrument we keep the better strategy's OOS result and flag genuine edges.

Vol targeting is applied per our rule: ON for mean-reversion, OFF for trend.
Screening grids are intentionally small (we're finding edges, not fine-tuning).
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.loader import fetch_okx_ohlcv
from src.data.yahoo_loader import fetch_yahoo_h4, INSTRUMENTS, CRYPTO_INSTRUMENTS
from src.strategy.ema_rsi_swing import EmaRsiSwing
from src.strategy.mean_reversion import BollingerMeanReversion
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.risk.vol_target import volatility_target_scalar
from src.backtest.engine import CostModel, BacktestConfig
from src.backtest.walk_forward import walk_forward

SPEC = SymbolSpec(tick_size=1.0, tick_value=1.0, volume_min=1e-6, volume_step=1e-6, volume_max=1e12)
RISK = RiskParams(2.0, 5.0, MinLotPolicy.MIN)

TREND = {"fast": [10, 20], "slow": [50], "sl_atr_mult": [2.0, 2.5, 3.0],
         "tp_rr": [1.5, 2.0, 3.0], "use_htf_filter": [True], "htf_rule": ["1D"],
         "htf_ema_period": [50]}
MEANREV = {"period": [20], "num_std": [2.0, 2.5], "rsi_oversold": [30.0],
           "rsi_overbought": [70.0], "sl_atr_mult": [2.0, 3.0], "tp_rr": [1.0, 1.5]}


def spread_for(cls: str) -> float:
    return {"forex": 0.0001, "commodity": 0.0004, "index": 0.0002, "crypto": 0.0004}[cls]


def wf(df, factory, grid, bpy, cost, vs, isb, oosb, step):
    cfg = BacktestConfig(initial_balance=100_000.0, bars_per_year=bpy, allow_short=True)
    return walk_forward(df, factory, grid, SPEC, RISK, CostModel(spread_frac=cost), cfg,
                        is_bars=isb, oos_bars=oosb, step_bars=step, min_trades_is=8,
                        vol_scalar=vs)


def blend_portfolio(equities: dict) -> None:
    """Equal-weight the keepers' OOS equity curves and report the diversification
    benefit (blended Sharpe/drawdown vs the average of the individual edges)."""
    import numpy as np
    import pandas as pd

    daily = {}
    ind_sharpes = []
    for name, eq in equities.items():
        if eq is None or len(eq) < 10:
            continue
        s = pd.Series(eq.values, index=pd.to_datetime(eq.index))
        r = s.resample("1D").last().ffill().pct_change()
        daily[name] = r
        if r.std() > 0:
            ind_sharpes.append(r.mean() / r.std() * np.sqrt(252))
    if not daily:
        return
    dfp = pd.DataFrame(daily).fillna(0.0)
    port = dfp.mean(axis=1)                       # equal risk weight
    curve = (1 + port).cumprod()
    sharpe = port.mean() / port.std() * np.sqrt(252) if port.std() > 0 else 0.0
    peak = curve.cummax()
    maxdd = float(((curve - peak) / peak).min() * -100)
    total = float((curve.iloc[-1] - 1) * 100)

    print("\n=== BLENDED PORTFOLIO (equal-weight keepers) ===")
    print(f"  Instruments blended ... {dfp.shape[1]}")
    print(f"  Avg individual Sharpe . {np.mean(ind_sharpes):.2f}")
    print(f"  BLENDED Sharpe ........ {sharpe:.2f}   <- diversification benefit")
    print(f"  Blended max drawdown .. {maxdd:.2f}%")
    print(f"  Blended total return .. {total:+.2f}% (over overlapping period)")


def is_keeper(r) -> bool:
    return r.num_trades >= 10 and r.profit_factor >= 1.2 and r.sharpe >= 0.4 and r.total_return_pct > 0


def main() -> None:
    rows = []
    # Build the work list: (name, loader-callable, class, bars/yr)
    work = []
    for name, (ysym, jm, cls) in INSTRUMENTS.items():
        if name == "NIKKEI":
            continue
        work.append((name, lambda y=ysym: fetch_yahoo_h4(y), cls, 5 * 252))
    for name, inst in CRYPTO_INSTRUMENTS.items():
        work.append((name, lambda i=inst: fetch_okx_ohlcv(i, "H4", 6000), "crypto", 6 * 365))

    print(f"{'Instrument':<9} {'Class':<10} {'BEST':<10} {'PF':>5} {'Exp(R)':>7} "
          f"{'Return':>8} {'MaxDD':>7} {'Sharpe':>6}  keep")
    print("-" * 78)
    keepers = []
    keeper_equity = {}
    for name, load, cls, bpy in work:
        df = load()
        n = len(df)
        if cls == "crypto":
            isb, oosb, step = 1500, 500, 500
        elif n < 2000:
            isb, oosb, step = 700, 250, 250
        else:
            isb, oosb, step = 1000, 350, 350
        vs = volatility_target_scalar(df["close"], lookback=14, median_window=500)
        cost = spread_for(cls)

        tr_res = wf(df, EmaRsiSwing, TREND, bpy, cost, None, isb, oosb, step)         # trend: vol-tgt OFF
        mr_res = wf(df, BollingerMeanReversion, MEANREV, bpy, cost, vs, isb, oosb, step)  # MR: vol-tgt ON
        tr, mr = tr_res.oos_report, mr_res.oos_report

        if tr.sharpe >= mr.sharpe:
            best_kind, best, best_res = "trend", tr, tr_res
        else:
            best_kind, best, best_res = "mean-rev", mr, mr_res
        keep = is_keeper(best)
        if keep:
            keepers.append((name, cls, best_kind, best))
            keeper_equity[name] = best_res.oos_equity
        print(f"{name:<9} {cls:<10} {best_kind:<10} {best.profit_factor:>5.2f} "
              f"{best.expectancy_r:>+7.3f} {best.total_return_pct:>+7.2f}% "
              f"{best.max_drawdown_pct:>6.2f}% {best.sharpe:>6.2f}  {'YES' if keep else ''}")

    print(f"\n=== KEEPERS ({len(keepers)}) ===")
    for name, cls, kind, r in sorted(keepers, key=lambda x: -x[3].sharpe):
        print(f"  {name:<9} {cls:<10} {kind:<9} Sharpe {r.sharpe:.2f}  ret {r.total_return_pct:+.1f}%  DD {r.max_drawdown_pct:.1f}%")

    blend_portfolio(keeper_equity)


if __name__ == "__main__":
    main()
