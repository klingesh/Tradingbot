"""
Lightweight CSV journal for the live bot.

Records every decision/action and periodic equity snapshots so we can review
what the bot did and plot a live equity curve. Written to logs/ (gitignored).

This is the bot's OWN record. For realized P&L the source of truth is the
broker's deal history (see MT5Connector.closed_deals + scripts/report.py).
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone

_FIELDS = [
    "timestamp", "kind", "symbol", "action", "side", "lots",
    "price", "sl", "tp", "balance", "equity", "retcode", "reason",
]


class CSVJournal:
    def __init__(self, path: str = "logs/journal.csv"):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=_FIELDS).writeheader()

    def _write(self, row: dict) -> None:
        full = {k: row.get(k, "") for k in _FIELDS}
        full["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self.path, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=_FIELDS).writerow(full)

    def log_equity(self, balance: float, equity: float) -> None:
        self._write({"kind": "equity", "balance": balance, "equity": equity})

    def log_action(
        self, symbol: str, action: str, side: int = 0, lots: float = 0.0,
        price: float = 0.0, sl: float = 0.0, tp: float = 0.0,
        retcode="", reason: str = "",
    ) -> None:
        self._write({
            "kind": "action", "symbol": symbol, "action": action, "side": side,
            "lots": lots, "price": price, "sl": sl, "tp": tp,
            "retcode": retcode, "reason": reason,
        })

    def log_event(self, event: str, reason: str = "", balance: float = 0.0,
                  equity: float = 0.0) -> None:
        """Record something that happened to the bot rather than to a position.

        Kill switches, daily-loss halts, starts and restarts. These used to exist
        only as console output, so the single most important thing the bot can do
        -- stop itself -- left no trace once the window scrolled. A halt belongs in
        the same timeline as the trades that caused it.
        """
        self._write({
            "kind": "event", "action": event, "reason": reason,
            "balance": balance, "equity": equity,
        })
