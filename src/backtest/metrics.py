"""Performance metrics. The numbers that actually decide if a strategy is worth it."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List

import numpy as np
import pandas as pd


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: int              # +1 long, -1 short
    entry: float
    exit: float
    lots: float
    pnl: float             # account-currency P&L (after costs)
    r_multiple: float      # pnl / risk_amount  (how many "R" won/lost)
    reason: str            # tp / sl / signal_flip / end


@dataclass
class BacktestReport:
    initial_balance: float
    final_balance: float
    num_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    expectancy_per_trade: float     # avg currency P&L per trade
    expectancy_r: float             # avg R per trade  <-- the key edge metric
    total_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    avg_win_r: float
    avg_loss_r: float

    def as_dict(self) -> dict:
        return asdict(self)

    def pretty(self) -> str:
        # A real edge needs meaningfully positive expectancy AND profit factor > 1.
        if self.profit_factor > 1.05 and self.expectancy_r > 0.03:
            edge = "POSITIVE EDGE"
        elif self.profit_factor >= 0.97:
            edge = "BREAK-EVEN (no real edge)"
        else:
            edge = "NEGATIVE (losing)"
        return (
            "\n==================== BACKTEST REPORT ====================\n"
            f"  Trades taken .......... {self.num_trades}\n"
            f"  Win rate .............. {self.win_rate:6.2f}%\n"
            f"  Profit factor ......... {self.profit_factor:6.2f}   (>1 = profitable)\n"
            f"  Avg win / avg loss .... {self.avg_win:,.2f} / {self.avg_loss:,.2f}\n"
            f"  Avg win / loss (R) .... {self.avg_win_r:+.2f}R / {self.avg_loss_r:+.2f}R\n"
            "  ----------------------------------------------------\n"
            f"  EXPECTANCY / trade .... {self.expectancy_per_trade:,.2f}\n"
            f"  EXPECTANCY (R) ........ {self.expectancy_r:+.3f}R   <-- {edge}\n"
            "  ----------------------------------------------------\n"
            f"  Total return .......... {self.total_return_pct:+.2f}%\n"
            f"  Max drawdown .......... {self.max_drawdown_pct:.2f}%\n"
            f"  Sharpe (annualized) ... {self.sharpe:.2f}\n"
            f"  Balance ............... {self.initial_balance:,.0f} -> {self.final_balance:,.0f}\n"
            "=========================================================\n"
        )


def build_report(
    trades: List[Trade],
    equity_curve: pd.Series,
    initial_balance: float,
    bars_per_year: float,
) -> BacktestReport:
    n = len(trades)
    if n == 0:
        return BacktestReport(
            initial_balance, initial_balance, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        )

    pnls = np.array([t.pnl for t in trades])
    rs = np.array([t.r_multiple for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    win_rate = len(wins) / n * 100.0
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = losses.mean() if len(losses) else 0.0
    gross_profit = wins.sum()
    gross_loss = -losses.sum()
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    final_balance = float(equity_curve.iloc[-1])
    total_return_pct = (final_balance / initial_balance - 1.0) * 100.0

    # Max drawdown from the equity curve.
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    max_dd_pct = abs(drawdown.min()) * 100.0

    # Sharpe from per-bar equity returns.
    bar_returns = equity_curve.pct_change().dropna()
    if bar_returns.std() > 0:
        sharpe = bar_returns.mean() / bar_returns.std() * np.sqrt(bars_per_year)
    else:
        sharpe = 0.0

    return BacktestReport(
        initial_balance=initial_balance,
        final_balance=final_balance,
        num_trades=n,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        expectancy_per_trade=float(pnls.mean()),
        expectancy_r=float(rs.mean()),
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_dd_pct,
        sharpe=float(sharpe),
        avg_win_r=float(rs[rs > 0].mean()) if (rs > 0).any() else 0.0,
        avg_loss_r=float(rs[rs < 0].mean()) if (rs < 0).any() else 0.0,
    )
