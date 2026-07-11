"""
Run a backtest of the EMA+RSI swing strategy on real BTC H4 data.

Usage:
    python backtest_run.py
"""

from __future__ import annotations

from src.data.loader import fetch_okx_ohlcv
from src.strategy.ema_rsi_swing import EmaRsiSwing
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.backtest.engine import run_backtest, CostModel, BacktestConfig


# Illustrative BTC CFD spec. Real values come from MT5 symbol_info later.
# value_per_point = tick_value / tick_size = 1.0 currency unit per price unit per lot.
BTC_SPEC = SymbolSpec(
    tick_size=0.1,
    tick_value=0.1,
    volume_min=0.01,
    volume_step=0.01,
    volume_max=100.0,
)


def main() -> None:
    print("Loading BTC-USDT H4 data...")
    df = fetch_okx_ohlcv(inst_id="BTC-USDT", timeframe="H4", bars=6000)
    print(f"  {len(df)} bars  {df.index[0].date()} -> {df.index[-1].date()}")

    strategy = EmaRsiSwing(fast=20, slow=50, sl_atr_mult=2.5, tp_rr=2.0)
    risk = RiskParams(
        risk_percent_per_trade=2.0,
        max_risk_percent_per_trade=5.0,
        on_min_lot_exceeds_risk=MinLotPolicy.MIN,  # keep all trades for evaluation
    )
    cost = CostModel(spread_frac=0.0004)  # ~0.04% adverse fill per side
    config = BacktestConfig(initial_balance=100_000.0, allow_short=True)

    report, trades, equity = run_backtest(df, strategy, BTC_SPEC, risk, cost, config)
    print(report.pretty())

    if trades:
        exits = {}
        for t in trades:
            exits[t.reason] = exits.get(t.reason, 0) + 1
        print("  Exit breakdown:", exits)


if __name__ == "__main__":
    main()
