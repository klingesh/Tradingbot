"""
Walk-forward validation of the FVG (Fair Value Gap) continuation strategy,
mined from the EA repo's SMC indicators. Does it hold up OUT-OF-SAMPLE, and does
it beat/complement our existing edges?

Tested on crypto (BTC H4, OKX) + gold/silver/AUDUSD/USDJPY (H4, Yahoo).
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.loader import fetch_okx_ohlcv
from src.data.yahoo_loader import fetch_yahoo_h4, INSTRUMENTS
from src.strategy.fvg import FvgContinuation
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.backtest.engine import CostModel, BacktestConfig
from src.backtest.walk_forward import walk_forward

RESEARCH_SPEC = SymbolSpec(tick_size=1.0, tick_value=1.0,
                           volume_min=1e-6, volume_step=1e-6, volume_max=1e12)
RISK = RiskParams(risk_percent_per_trade=2.0, max_risk_percent_per_trade=5.0,
                  on_min_lot_exceeds_risk=MinLotPolicy.MIN)

FVG_GRID = {
    "sl_atr_mult": [2.0, 2.5, 3.0],
    "tp_rr": [1.5, 2.0, 3.0],
    "max_zone_age": [20, 50],
    "min_gap_atr": [0.0, 0.5],
    "use_htf_filter": [True],
    "htf_rule": ["1D"],
    "htf_ema_period": [50],
}


def row(name, r):
    return (f"{name:<10} {r.num_trades:>6} {r.win_rate:>5.1f}% {r.profit_factor:>5.2f} "
            f"{r.expectancy_r:>+7.3f} {r.total_return_pct:>+8.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe:>6.2f}")


def main() -> None:
    print(f"{'Instrument':<10} {'Trades':>6} {'Win':>6} {'PF':>5} {'Exp(R)':>7} "
          f"{'Return':>9} {'MaxDD':>7} {'Sharpe':>6}")
    print("-" * 74)

    # Crypto (more bars).
    df = fetch_okx_ohlcv("BTC-USDT", "H4", 6000)
    cfg_c = BacktestConfig(initial_balance=100_000.0, bars_per_year=6 * 365, allow_short=True)
    res = walk_forward(df, FvgContinuation, FVG_GRID, RESEARCH_SPEC, RISK,
                       CostModel(spread_frac=0.0004), cfg_c,
                       is_bars=1500, oos_bars=500, step_bars=500, min_trades_is=12)
    print(row("BTC", res.oos_report))

    # Forex + commodities (H4, ~2yr).
    cfg_f = BacktestConfig(initial_balance=100_000.0, bars_per_year=5 * 252, allow_short=True)
    for name in ("XAUUSD", "XAGUSD", "AUDUSD", "USDJPY"):
        ysym, _, cls = INSTRUMENTS[name]
        df = fetch_yahoo_h4(ysym)
        cost = CostModel(spread_frac=0.0001 if cls == "forex" else 0.0004)
        res = walk_forward(df, FvgContinuation, FVG_GRID, RESEARCH_SPEC, RISK, cost, cfg_f,
                           is_bars=1000, oos_bars=350, step_bars=350, min_trades_is=10)
        print(row(name, res.oos_report))

    print("\n(OOS = out-of-sample. Compare to portfolio: Gold trend +13.9%/1.35,")
    print(" AUDUSD MR +18.9%/1.27, USDJPY MR +17.9%/1.18, Silver trend +11%/0.85, BTC trend +22.8%/0.84)")


if __name__ == "__main__":
    main()
