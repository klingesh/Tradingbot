"""
Walk-forward validation of two more EA-mined concept families:
  * Order Block continuation (SMC / supply-demand)
  * Liquidity Sweep reversal (ICT stop-hunt)

Tested OOS across BTC (H4) + gold/silver/AUDUSD/USDJPY (H4), compared to the
existing portfolio edges. Disciplined: a concept only "wins" if it's positive
OOS on several instruments AND beats/complements what we already run.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.loader import fetch_okx_ohlcv
from src.data.yahoo_loader import fetch_yahoo_h4, INSTRUMENTS
from src.strategy.order_block import OrderBlockContinuation
from src.strategy.liquidity_sweep import LiquiditySweepReversal
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.backtest.engine import CostModel, BacktestConfig
from src.backtest.walk_forward import walk_forward

SPEC = SymbolSpec(tick_size=1.0, tick_value=1.0, volume_min=1e-6, volume_step=1e-6, volume_max=1e12)
RISK = RiskParams(2.0, 5.0, MinLotPolicy.MIN)

OB_GRID = {
    "sl_atr_mult": [2.0, 2.5, 3.0], "tp_rr": [1.5, 2.0, 3.0],
    "impulse_atr": [1.0, 1.5], "max_zone_age": [20, 50],
    "use_htf_filter": [True], "htf_rule": ["1D"], "htf_ema_period": [50],
}
SWEEP_GRID = {
    "lookback": [10, 20, 30], "sl_atr_mult": [1.5, 2.0, 3.0],
    "tp_rr": [1.5, 2.0, 3.0], "use_htf_filter": [True, False],
}

INSTR = [("BTC", None, 6 * 365, 1500, 500, 500, 0.0004),
         ("XAUUSD", "commodity", 5 * 252, 1000, 350, 350, 0.0004),
         ("XAGUSD", "commodity", 5 * 252, 1000, 350, 350, 0.0004),
         ("AUDUSD", "forex", 5 * 252, 1000, 350, 350, 0.0001),
         ("USDJPY", "forex", 5 * 252, 1000, 350, 350, 0.0001)]


def load(name):
    if name == "BTC":
        return fetch_okx_ohlcv("BTC-USDT", "H4", 6000)
    return fetch_yahoo_h4(INSTRUMENTS[name][0])


def run_family(title, factory, grid):
    print(f"\n===== {title} =====")
    print(f"{'Instrument':<10} {'Trades':>6} {'Win':>6} {'PF':>5} {'Exp(R)':>7} "
          f"{'Return':>9} {'MaxDD':>7} {'Sharpe':>6}")
    print("-" * 74)
    for name, cls, bpy, isb, oosb, step, spread in INSTR:
        df = load(name)
        cfg = BacktestConfig(initial_balance=100_000.0, bars_per_year=bpy, allow_short=True)
        res = walk_forward(df, factory, grid, SPEC, RISK, CostModel(spread_frac=spread), cfg,
                           is_bars=isb, oos_bars=oosb, step_bars=step, min_trades_is=10)
        r = res.oos_report
        print(f"{name:<10} {r.num_trades:>6} {r.win_rate:>5.1f}% {r.profit_factor:>5.2f} "
              f"{r.expectancy_r:>+7.3f} {r.total_return_pct:>+8.2f}% "
              f"{r.max_drawdown_pct:>6.2f}% {r.sharpe:>6.2f}")


def main() -> None:
    run_family("ORDER BLOCK continuation (SMC)", OrderBlockContinuation, OB_GRID)
    run_family("LIQUIDITY SWEEP reversal (ICT)", LiquiditySweepReversal, SWEEP_GRID)
    print("\nPortfolio benchmark: Gold trend +13.9%/1.35 | AUDUSD MR +18.9%/1.27 |")
    print("USDJPY MR +17.9%/1.18 | Silver trend +11%/0.85 | BTC trend +22.8%/0.84")


if __name__ == "__main__":
    main()
