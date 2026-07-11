"""
Experiment: compare strategy archetypes on the same BTC H4 data.

Trend-following (EMA+RSI), breakout (Donchian), and mean-reversion (Bollinger),
each with and without the daily trend filter where it makes sense.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.loader import fetch_okx_ohlcv
from src.strategy import EmaRsiSwing, DonchianBreakout, BollingerMeanReversion
from src.risk.position_sizing import SymbolSpec, RiskParams, MinLotPolicy
from src.backtest.engine import run_backtest, CostModel, BacktestConfig

BTC_SPEC = SymbolSpec(tick_size=0.1, tick_value=0.1, volume_min=0.01, volume_step=0.01, volume_max=100.0)
RISK = RiskParams(risk_percent_per_trade=2.0, max_risk_percent_per_trade=5.0,
                  on_min_lot_exceeds_risk=MinLotPolicy.MIN)
COST = CostModel(spread_frac=0.0004)
CONFIG = BacktestConfig(initial_balance=100_000.0, allow_short=True)


def row(label: str, rep) -> str:
    return (f"{label:<34} {rep.num_trades:>5}  {rep.win_rate:>6.2f}%  "
            f"{rep.profit_factor:>5.2f}  {rep.expectancy_r:>+7.3f}R  "
            f"{rep.total_return_pct:>+8.2f}%  {rep.max_drawdown_pct:>6.2f}%  {rep.sharpe:>5.2f}")


def main() -> None:
    df = fetch_okx_ohlcv(inst_id="BTC-USDT", timeframe="H4", bars=6000)
    print(f"Data: {len(df)} H4 bars  {df.index[0].date()} -> {df.index[-1].date()}\n")

    print(f"{'Strategy':<34} {'Trades':>5}  {'Win':>6}  {'PF':>5}  {'Exp(R)':>8}  {'Return':>8}  {'MaxDD':>6}  {'Sharpe':>5}")
    print("-" * 98)

    variants = {
        "EMA+RSI (no filter)":            EmaRsiSwing(sl_atr_mult=2.5, tp_rr=2.0),
        "EMA+RSI + daily filter":         EmaRsiSwing(sl_atr_mult=2.5, tp_rr=2.0, use_htf_filter=True),
        "Donchian breakout (no filter)":  DonchianBreakout(channel=20, sl_atr_mult=2.5, tp_rr=2.0),
        "Donchian breakout + daily filter": DonchianBreakout(channel=20, sl_atr_mult=2.5, tp_rr=2.0, use_htf_filter=True),
        "Bollinger mean-reversion":       BollingerMeanReversion(sl_atr_mult=2.5, tp_rr=1.0),
    }

    for label, strat in variants.items():
        rep, _, _ = run_backtest(df, strat, BTC_SPEC, RISK, COST, CONFIG)
        print(row(label, rep))


if __name__ == "__main__":
    main()
