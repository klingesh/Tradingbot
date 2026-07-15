"""
Live performance report.

Pulls the bot's actual closed trades from the broker (source of truth) and
prints live stats - win rate, profit factor, net P&L, per-symbol breakdown -
plus an equity-curve summary from the bot's journal. Compare these to the
backtest expectations in docs/RESEARCH_FINDINGS.md.

Usage (Windows, MT5 running):
    python scripts/report.py            # last 30 days
    python scripts/report.py --days 90
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.connectors import MT5Connector


def _equity_summary(path: str = "logs/journal.csv") -> None:
    if not os.path.exists(path):
        print("  (no journal yet - run the bot to build an equity curve)")
        return
    eq = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row.get("kind") == "equity" and row.get("equity"):
                try:
                    eq.append(float(row["equity"]))
                except ValueError:
                    pass
    if not eq:
        print("  (no equity snapshots yet)")
        return
    peak = eq[0]
    max_dd = 0.0
    for e in eq:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak * 100 if peak else 0.0)
    print(f"  snapshots: {len(eq)}   first: {eq[0]:,.2f}   last: {eq[-1]:,.2f}   "
          f"peak: {max(eq):,.2f}   min: {min(eq):,.2f}")
    print(f"  equity max drawdown so far: {max_dd:.2f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    c = MT5Connector()
    if not c.available():
        print("MetaTrader5 not available (run on Windows).")
        return
    acct = c.connect()
    print(f"Account {acct.login}   Balance {acct.balance:,.2f} {acct.currency}   "
          f"Equity {acct.equity:,.2f}\n")

    deals = c.closed_deals(days=args.days)
    print(f"=== LIVE PERFORMANCE (bot trades, last {args.days} days) ===")
    if not deals:
        print("  No closed bot trades yet. Let it run (swing trades are infrequent).")
        c.shutdown()
        print("\n=== EQUITY CURVE (from journal) ===")
        _equity_summary()
        return

    net = [d["profit"] + d["commission"] + d["swap"] for d in deals]
    wins = [p for p in net if p > 0]
    losses = [p for p in net if p < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    n = len(net)
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    print(f"  Trades ............ {n}")
    print(f"  Win rate .......... {len(wins)/n*100:.1f}%")
    print(f"  Profit factor ..... {pf:.2f}")
    print(f"  Gross profit ...... {gross_profit:,.2f}")
    print(f"  Gross loss ........ {gross_loss:,.2f}")
    print(f"  NET P&L ........... {sum(net):,.2f} {acct.currency}")
    print(f"  Avg win / loss .... {(sum(wins)/len(wins) if wins else 0):,.2f} / "
          f"{(sum(losses)/len(losses) if losses else 0):,.2f}")

    # Per-symbol breakdown.
    by_sym: dict[str, list[float]] = {}
    for d, p in zip(deals, net):
        by_sym.setdefault(d["symbol"], []).append(p)
    print("\n  Per symbol:")
    for sym, pnls in sorted(by_sym.items()):
        w = sum(1 for x in pnls if x > 0)
        print(f"    {sym:<14} trades={len(pnls):>3}  win%={w/len(pnls)*100:5.1f}  "
              f"net={sum(pnls):+,.2f}")

    print("\n=== EQUITY CURVE (from journal) ===")
    _equity_summary()
    c.shutdown()


if __name__ == "__main__":
    main()
