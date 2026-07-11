"""
Walk-forward validation of the EMA+RSI + daily-filter swing strategy on BTC H4.

The real question: does the edge survive on data the optimizer never saw?
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.loader import fetch_okx_ohlcv
from src.strategy.ema_rsi_swing import EmaRsiSwing
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.backtest.engine import CostModel, BacktestConfig
from src.backtest.walk_forward import walk_forward

BTC_SPEC = SymbolSpec(tick_size=0.1, tick_value=0.1, volume_min=0.01, volume_step=0.01, volume_max=100.0)
RISK = RiskParams(risk_percent_per_trade=2.0, max_risk_percent_per_trade=5.0,
                  on_min_lot_exceeds_risk=MinLotPolicy.MIN)
COST = CostModel(spread_frac=0.0004)
CONFIG = BacktestConfig(initial_balance=100_000.0, allow_short=True)

# Parameter grid searched IN-SAMPLE each fold. HTF filter always on.
PARAM_GRID = {
    "fast": [10, 20],
    "slow": [50, 100],
    "sl_atr_mult": [2.0, 2.5, 3.0],
    "tp_rr": [1.5, 2.0, 3.0],
    "use_htf_filter": [True],
    "htf_ema_period": [50],
}


def main() -> None:
    df = fetch_okx_ohlcv(inst_id="BTC-USDT", timeframe="H4", bars=6000)
    print(f"Data: {len(df)} H4 bars  {df.index[0].date()} -> {df.index[-1].date()}")
    combos = 1
    for v in PARAM_GRID.values():
        combos *= len(list(v))
    print(f"Grid: {combos} param combos optimized per fold "
          f"(objective = expectancy_r)\n")

    result = walk_forward(
        df, EmaRsiSwing, PARAM_GRID, BTC_SPEC, RISK, COST, CONFIG,
        is_bars=1500, oos_bars=500, step_bars=500,
    )

    print("Per-fold OUT-OF-SAMPLE results (data never used for tuning):")
    print(f"{'OOS window':<26} {'Trades':>6} {'Win':>6} {'PF':>5} {'Exp(R)':>8} {'Return':>8}  params")
    print("-" * 100)
    for f in result.fold_summaries:
        p = f["params"]
        ptxt = f"f{p['fast']}/s{p['slow']} sl{p['sl_atr_mult']} rr{p['tp_rr']}"
        print(f"{f['oos_start']+' -> '+f['oos_end']:<26} {f['oos_trades']:>6} "
              f"{f['oos_win']:>5}% {f['oos_pf']:>5} {f['oos_exp_r']:>+8} "
              f"{f['oos_return_pct']:>+7}%  {ptxt}")

    print("\n" + "=" * 60)
    print("AGGREGATE OUT-OF-SAMPLE PERFORMANCE (the honest number):")
    print(result.oos_report.pretty())


if __name__ == "__main__":
    main()
