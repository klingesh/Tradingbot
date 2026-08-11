"""State that has to outlive the process.

Two things go wrong when a 24/7 bot keeps all its safety state in memory.

**The kill switch can be reset by a crash.** `run_bot.bat` restarts the bot thirty
seconds after any exit, forever. The drawdown baseline used to be taken from
whatever the balance happened to be at connect time, so a bot that had drawn down
15%, hit an MT5 disconnect and restarted would measure its next drawdown from the
already-reduced balance -- and could lose another 20% before the switch that was
meant to stop it fired. Over two weeks of unattended running that is not a
hypothetical. The same applied to the halt itself: `_halted` reset to False on
restart, so a halted bot resumed trading half a minute later.

**Nothing durable records what happened.** Logging went to the console only, and
the restart wrapper does not redirect it, so a kill-switch message scrolled away
with the window.

So the baseline, the halt and the day's opening equity are kept in
`logs/state.json`, and a companion `logs/status.json` is written every cycle for
anything that wants to know how the bot is doing without attaching to MT5.

The baseline is a **high-water mark**: it rises when the balance rises (a deposit,
or genuine profit) and never falls on a restart. To start it over -- after resetting
a demo account, say -- delete `logs/state.json`.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STATE_PATH = "logs/state.json"
STATUS_PATH = "logs/status.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_atomic(path: str, payload: Dict[str, Any]) -> None:
    """Write JSON so a reader never sees a half-written file.

    The monitor may read this at any moment, including mid-write. Writing to a
    temporary file in the same directory and renaming makes the swap atomic on
    both Windows and Linux.
    """
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@dataclass
class BotState:
    """Safety state that must survive a restart."""

    #: High-water mark of account balance; the kill switch measures against this.
    start_balance: Optional[float] = None
    #: Highest equity ever seen, for reporting drawdown.
    peak_equity: Optional[float] = None
    #: True once the total-drawdown kill switch has fired. Never cleared
    #: automatically -- a halted bot stays halted until a human clears it.
    halted: bool = False
    halt_reason: str = ""
    halted_at: str = ""
    #: UTC date (ISO) the daily-loss baseline belongs to.
    day: str = ""
    day_start_equity: Optional[float] = None
    #: True once the daily-loss limit has tripped today.
    day_halted: bool = False
    #: Rolling record of the last few faults, newest last.
    recent_errors: List[Dict[str, str]] = field(default_factory=list)
    started_at: str = ""
    restarts: int = 0

    # ---- persistence ----
    @classmethod
    def load(cls, path: str = STATE_PATH) -> "BotState":
        """Read saved state. A missing or corrupt file yields a fresh state.

        Corruption must not stop the bot starting, but it also must not silently
        hand back a zeroed baseline that quietly disarms the kill switch, so the
        caller is told by way of an error entry.
        """
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            return cls()
        except Exception as exc:
            fresh = cls()
            fresh.note_error("state", f"could not read {path}: {exc}")
            return fresh

        known = {f for f in cls.__dataclass_fields__}
        state = cls(**{k: v for k, v in raw.items() if k in known})
        return state

    def save(self, path: str = STATE_PATH) -> None:
        _write_atomic(path, asdict(self))

    # ---- baseline ----
    def sync_baseline(self, balance: float) -> None:
        """Set or raise the drawdown baseline for this balance.

        Raising it on a new high is deliberate: real profit or a deposit should
        move the goalposts up. Never lowering it is the whole point -- that is what
        stops a restart from forgiving a drawdown that already happened.
        """
        if self.start_balance is None or balance > self.start_balance:
            self.start_balance = float(balance)
        if self.peak_equity is None or balance > self.peak_equity:
            self.peak_equity = float(balance)

    def note_equity(self, equity: float) -> None:
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = float(equity)

    def drawdown_percent(self, equity: float) -> float:
        """Drawdown from the baseline, in percent. 0.0 when unknown or in profit."""
        if not self.start_balance:
            return 0.0
        dd = (self.start_balance - equity) / self.start_balance * 100.0
        return max(0.0, dd)

    # ---- halting ----
    def halt(self, reason: str) -> bool:
        """Record a kill-switch halt. Returns True the first time only.

        The return value keeps the log honest: without it the halt message was
        emitted on every poll, which at sixty-second intervals buried everything
        else under fourteen hundred identical lines a day.
        """
        if self.halted:
            return False
        self.halted = True
        self.halt_reason = reason
        self.halted_at = _now()
        return True

    def roll_day(self, today: str, equity: float) -> bool:
        """Start a new trading day if the date has changed. Returns True if rolled."""
        if self.day == today:
            return False
        self.day = today
        self.day_start_equity = float(equity)
        self.day_halted = False
        return True

    def day_drawdown_percent(self, equity: float) -> float:
        if not self.day_start_equity:
            return 0.0
        dd = (self.day_start_equity - equity) / self.day_start_equity * 100.0
        return max(0.0, dd)

    def halt_day(self, reason: str) -> bool:
        """Record the daily-loss halt. Returns True only the first time today."""
        if self.day_halted:
            return False
        self.day_halted = True
        return True

    # ---- faults ----
    def note_error(self, where: str, message: str, keep: int = 20) -> None:
        self.recent_errors.append({
            "at": _now(), "where": str(where), "message": str(message)[:400],
        })
        del self.recent_errors[:-keep]


def write_status(
    state: BotState,
    *,
    balance: float = 0.0,
    equity: float = 0.0,
    currency: str = "",
    login: Any = "",
    dry_run: bool = True,
    halt_new: bool = False,
    open_positions: Optional[List[Dict[str, Any]]] = None,
    max_daily_loss_percent: float = 0.0,
    max_total_drawdown_percent: float = 0.0,
    path: str = STATUS_PATH,
) -> None:
    """Publish a snapshot of how the bot is doing.

    Deliberately a separate file from state.json. This one is a report -- safe to
    copy, upload or read from another machine -- while state.json is the bot's own
    working memory. Keeping them apart means a monitor can never corrupt the
    safety state by touching the thing it reads.

    `heartbeat_age_seconds` is the field that matters most to a watcher: the bot
    rewrites this every poll, so a stale timestamp is the only reliable way to
    tell from outside that the process has stopped.
    """
    positions = open_positions or []
    payload = {
        "heartbeat": _now(),
        "poll_note": "rewritten every cycle; a stale heartbeat means stopped",
        "login": login,
        "currency": currency,
        "dry_run": bool(dry_run),
        "balance": round(float(balance), 2),
        "equity": round(float(equity), 2),
        "peak_equity": round(float(state.peak_equity), 2) if state.peak_equity else None,
        "baseline_balance": (round(float(state.start_balance), 2)
                             if state.start_balance else None),
        "drawdown_percent": round(state.drawdown_percent(equity), 2),
        "drawdown_limit_percent": float(max_total_drawdown_percent),
        "day": state.day,
        "day_drawdown_percent": round(state.day_drawdown_percent(equity), 2),
        "day_loss_limit_percent": float(max_daily_loss_percent),
        "halted": bool(state.halted),
        "halt_reason": state.halt_reason,
        "halted_at": state.halted_at,
        "day_halted": bool(state.day_halted),
        "new_entries_blocked": bool(halt_new),
        "open_positions": positions,
        "open_count": len(positions),
        "restarts": int(state.restarts),
        "started_at": state.started_at,
        "recent_errors": state.recent_errors[-5:],
    }
    _write_atomic(path, payload)
