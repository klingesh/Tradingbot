"""
Experiment: does a higher-timeframe (daily) trend filter improve the H4 swing edge?

Compares the baseline EMA+RSI strategy against the same strategy that only takes
trades aligned with the daily trend.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.loader import fetch_okx_ohlcv
from src.strategy.ema_rsi_swing import EmaRsiSwing
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.backtest.engine import run_backtest, CostModel, BacktestConfig

BTC_SPEC = SymbolSpec(tick_size=0.1, tick_value=0.1, volume_min=0.01, volume_step=0.01, volume_max=100.0)
RISK = RiskParams(risk_percent_per_trade=2.0, max_risk_percent_per_trade=5.0,
                  on_min_lot_exceeds_risk=MinLotPolicy.MIN)
COST = CostModel(spread_frac=0.0004)
CONFIG = BacktestConfig(initial_balance=100_000.0, allow_short=True)


def row(label: str, rep) -> str:
    return (f"{label:<28} {rep.num_trades:>5}  {rep.win_rate:>6.2f}%  "
            f"{rep.profit_factor:>5.2f}  {rep.expectancy_r:>+7.3f}R  "
            f"{rep.total_return_pct:>+8.2f}%  {rep.max_drawdown_pct:>6.2f}%  {rep.sharpe:>5.2f}")


def main() -> None:
    df = fetch_okx_ohlcv(inst_id="BTC-USDT", timeframe="H4", bars=6000)
    print(f"Data: {len(df)} H4 bars  {df.index[0].date()} -> {df.index[-1].date()}\n")

    print(f"{'Variant':<28} {'Trades':>5}  {'Win':>6}  {'PF':>5}  {'Exp(R)':>8}  {'Return':>8}  {'MaxDD':>6}  {'Sharpe':>5}")
    print("-" * 92)

    variants = {
        "Baseline (no filter)": EmaRsiSwing(fast=20, slow=50, sl_atr_mult=2.5, tp_rr=2.0),
        "+ Daily EMA50 filter": EmaRsiSwing(fast=20, slow=50, sl_atr_mult=2.5, tp_rr=2.0,
                                            use_htf_filter=True, htf_rule="1D", htf_ema_period=50),
        "+ Daily EMA100 filter": EmaRsiSwing(fast=20, slow=50, sl_atr_mult=2.5, tp_rr=2.0,
                                             use_htf_filter=True, htf_rule="1D", htf_ema_period=100),
    }

    for label, strat in variants.items():
        rep, _, _ = run_backtest(df, strat, BTC_SPEC, RISK, COST, CONFIG)
        print(row(label, rep))


if __name__ == "__main__":
    main()
