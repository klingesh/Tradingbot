"""
Walk-forward test of the EMA+RSI trend strategy on forex + commodities at the
H4 timeframe with a DAILY trend filter - apples-to-apples with the crypto setup
that produced the strong edge.

~2 years of H4 data (Yahoo hourly resampled), more trades than daily.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.yahoo_loader import fetch_yahoo_h4, INSTRUMENTS
from src.strategy.ema_rsi_swing import EmaRsiSwing
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.backtest.engine import CostModel, BacktestConfig
from src.backtest.walk_forward import walk_forward

RESEARCH_SPEC = SymbolSpec(tick_size=1.0, tick_value=1.0,
                           volume_min=1e-6, volume_step=1e-6, volume_max=1e12)
RISK = RiskParams(risk_percent_per_trade=2.0, max_risk_percent_per_trade=5.0,
                  on_min_lot_exceeds_risk=MinLotPolicy.MIN)
CONFIG = BacktestConfig(initial_balance=100_000.0, bars_per_year=5 * 252, allow_short=True)

# H4 + daily trend filter; grid optimizes the rest per fold.
PARAM_GRID = {
    "fast": [10, 20],
    "slow": [50, 100],
    "sl_atr_mult": [2.0, 2.5, 3.0],
    "tp_rr": [1.5, 2.0, 3.0],
    "use_htf_filter": [True],
    "htf_rule": ["1D"],
    "htf_ema_period": [50],
}


def cost_for(asset_class: str) -> CostModel:
    return CostModel(spread_frac=0.0001 if asset_class == "forex" else 0.0004)


def main() -> None:
    print(f"{'Instrument':<10} {'Class':<10} {'OOS Trades':>10} {'Win':>6} {'PF':>5} "
          f"{'Exp(R)':>8} {'Return':>9} {'MaxDD':>7} {'Sharpe':>6}")
    print("-" * 82)

    agg = {"ret": 0.0, "pf": 0.0, "exp": 0.0, "sharpe": 0.0, "n": 0}
    for name, (ysym, jm_symbol, cls) in INSTRUMENTS.items():
        df = fetch_yahoo_h4(ysym)
        res = walk_forward(
            df, EmaRsiSwing, PARAM_GRID, RESEARCH_SPEC, RISK, cost_for(cls), CONFIG,
            is_bars=1000, oos_bars=350, step_bars=350, min_trades_is=10,
        )
        r = res.oos_report
        print(f"{name:<10} {cls:<10} {r.num_trades:>10} {r.win_rate:>5.1f}% "
              f"{r.profit_factor:>5.2f} {r.expectancy_r:>+8.3f} "
              f"{r.total_return_pct:>+8.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe:>6.2f}")
        agg["ret"] += r.total_return_pct; agg["pf"] += r.profit_factor
        agg["exp"] += r.expectancy_r; agg["sharpe"] += r.sharpe; agg["n"] += 1

    n = agg["n"]
    print("-" * 82)
    print(f"{'AVERAGE':<10} {'':<10} {'':>10} {'':>6} {agg['pf']/n:>5.2f} "
          f"{agg['exp']/n:>+8.3f} {agg['ret']/n:>+8.2f}% {'':>7} {agg['sharpe']/n:>6.2f}")
    print("\n(OOS = out-of-sample. Compare to the DAILY results from the previous run.)")


if __name__ == "__main__":
    main()
