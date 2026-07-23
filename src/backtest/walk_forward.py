"""
Walk-forward analysis - the anti-overfitting test.

Procedure (rolling):
    1. Take an in-sample (IS) window of past bars.
    2. Grid-search parameters, pick the best by out-of-sample-safe objective.
    3. Apply those params to the NEXT out-of-sample (OOS) window - data the
       optimizer never saw.
    4. Roll the windows forward and repeat.
    5. Stitch all OOS segments into one continuous equity curve.

If the strategy is only profitable in-sample but falls apart out-of-sample,
it was curve-fit. If OOS holds up, the edge is more likely real.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable

import pandas as pd

from ..strategy.base import Strategy
from ..risk.position_sizing import SymbolSpec, RiskParams
from .engine import run_backtest, CostModel, BacktestConfig
from .metrics import Trade, build_report, BacktestReport


@dataclass
class WalkForwardResult:
    oos_report: BacktestReport
    oos_equity: pd.Series
    fold_summaries: list[dict]
    chosen_params: list[dict]


def walk_forward(
    df: pd.DataFrame,
    strategy_factory: Callable[..., Strategy],
    param_grid: dict[str, Iterable],
    symbol: SymbolSpec,
    risk: RiskParams,
    cost: CostModel,
    base_config: BacktestConfig,
    is_bars: int = 1500,
    oos_bars: int = 500,
    step_bars: int = 500,
    min_trades_is: int = 12,
    objective: str = "expectancy_r",
    blackout: "np.ndarray | None" = None,
    vol_scalar: "np.ndarray | None" = None,
) -> WalkForwardResult:
    keys = list(param_grid.keys())
    combos = [dict(zip(keys, vals)) for vals in product(*param_grid.values())]

    index = df.index
    n = len(df)

    running_balance = base_config.initial_balance
    all_oos_trades: list[Trade] = []
    oos_equity_segments: list[pd.Series] = []
    fold_summaries: list[dict] = []
    chosen_params: list[dict] = []

    start = 0
    while start + is_bars + oos_bars <= n:
        is_start_ts = index[start]
        oos_start_ts = index[start + is_bars]
        oos_end_ts = index[min(start + is_bars + oos_bars, n - 1)]

        # --- 1) Optimize on the in-sample window ---
        best = None
        for params in combos:
            strat = strategy_factory(**params)
            rep, trades, _ = run_backtest(
                df, strat, symbol, risk, cost, base_config,
                trade_start=is_start_ts, trade_end=oos_start_ts,
                blackout=blackout, vol_scalar=vol_scalar,
            )
            if rep.num_trades < min_trades_is:
                continue
            score = getattr(rep, objective)
            if best is None or score > best[0]:
                best = (score, params)

        chosen = best[1] if best else combos[0]
        chosen_params.append(chosen)

        # --- 2) Apply chosen params to the OOS window (carry balance forward) ---
        oos_config = BacktestConfig(
            initial_balance=running_balance,
            bars_per_year=base_config.bars_per_year,
            allow_short=base_config.allow_short,
        )
        strat = strategy_factory(**chosen)
        oos_rep, oos_trades, oos_eq = run_backtest(
            df, strat, symbol, risk, cost, oos_config,
            trade_start=oos_start_ts, trade_end=oos_end_ts,
            blackout=blackout, vol_scalar=vol_scalar,
        )

        all_oos_trades.extend(oos_trades)
        if len(oos_eq) > 0:
            oos_equity_segments.append(oos_eq)
            running_balance = float(oos_eq.iloc[-1])

        fold_summaries.append({
            "oos_start": str(oos_start_ts.date()),
            "oos_end": str(oos_end_ts.date()),
            "params": chosen,
            "oos_trades": oos_rep.num_trades,
            "oos_win": round(oos_rep.win_rate, 1),
            "oos_pf": round(oos_rep.profit_factor, 2),
            "oos_exp_r": round(oos_rep.expectancy_r, 3),
            "oos_return_pct": round(oos_rep.total_return_pct, 2),
        })

        start += step_bars

    oos_equity = pd.concat(oos_equity_segments) if oos_equity_segments else pd.Series(dtype=float)
    oos_report = build_report(
        all_oos_trades, oos_equity, base_config.initial_balance, base_config.bars_per_year
    )
    return WalkForwardResult(oos_report, oos_equity, fold_summaries, chosen_params)
