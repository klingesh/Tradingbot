"""Safety state must survive a restart.

The bot runs unattended behind run_bot.bat, which restarts it thirty seconds after
any exit. Before this state file existed, that wrapper could quietly disarm the
kill switch: the drawdown baseline was taken from whatever the balance happened to
be at connect time, so a crash after a loss forgave the loss.

The first test here is that scenario, written out step by step.
"""

from __future__ import annotations

import json

from src.live.state import BotState, write_status


def test_kill_switch_baseline_survives_a_crash(tmp_path):
    """The bug this file exists for.

    A bot draws down 15%, crashes, and is restarted by the wrapper. Its drawdown
    must still read 15% -- not zero.
    """
    path = str(tmp_path / "state.json")

    first = BotState.load(path)
    first.sync_baseline(10_000.0)
    assert first.drawdown_percent(8_500.0) == 15.0
    first.save(path)

    # ---- crash, then run_bot.bat starts a new process 30s later ----
    restarted = BotState.load(path)
    # The account is now worth 8,500. The old code took this as the new baseline.
    restarted.sync_baseline(8_500.0)

    assert restarted.start_balance == 10_000.0, "baseline was reset by the restart"
    assert restarted.drawdown_percent(8_500.0) == 15.0
    # And the switch still has only 5% of room left, not a fresh 20%.
    assert restarted.drawdown_percent(8_000.0) == 20.0


def test_baseline_rises_on_a_new_high_but_never_falls(tmp_path):
    path = str(tmp_path / "state.json")
    state = BotState.load(path)

    state.sync_baseline(10_000.0)
    state.sync_baseline(12_000.0)      # profit, or a deposit
    assert state.start_balance == 12_000.0

    state.sync_baseline(9_000.0)       # a loss must not move the goalposts down
    assert state.start_balance == 12_000.0
    assert state.drawdown_percent(9_000.0) == 25.0


def test_a_halt_survives_a_restart(tmp_path):
    path = str(tmp_path / "state.json")
    state = BotState.load(path)
    state.sync_baseline(10_000.0)

    assert state.halt("total drawdown 21% >= 20%") is True
    state.save(path)

    restarted = BotState.load(path)
    assert restarted.halted is True
    assert "21%" in restarted.halt_reason
    assert restarted.halted_at


def test_halt_reports_only_the_first_time(tmp_path):
    """Otherwise the halt line is logged on every poll -- 1440 times a day."""
    state = BotState()
    assert state.halt("first") is True
    assert state.halt("second") is False
    assert state.halt_reason == "first", "the original cause must not be overwritten"


def test_daily_loss_resets_on_a_new_day(tmp_path):
    state = BotState()

    assert state.roll_day("2026-08-11", 10_000.0) is True
    assert state.roll_day("2026-08-11", 9_000.0) is False, "same day must not reset"
    assert state.day_start_equity == 10_000.0
    assert state.day_drawdown_percent(9_400.0) == 6.0

    assert state.halt_day("daily loss 6%") is True
    assert state.halt_day("daily loss 7%") is False
    assert state.day_halted is True

    assert state.roll_day("2026-08-12", 9_400.0) is True
    assert state.day_halted is False, "a new day lifts the daily-loss halt"
    assert state.day_start_equity == 9_400.0


def test_drawdown_is_never_negative_and_is_safe_without_a_baseline():
    state = BotState()
    assert state.drawdown_percent(10_000.0) == 0.0, "no baseline yet"

    state.sync_baseline(10_000.0)
    assert state.drawdown_percent(11_000.0) == 0.0, "in profit is not drawdown"
    assert state.day_drawdown_percent(10_000.0) == 0.0


def test_peak_equity_tracks_the_high_water_mark():
    state = BotState()
    state.sync_baseline(10_000.0)
    state.note_equity(10_800.0)
    state.note_equity(10_200.0)
    assert state.peak_equity == 10_800.0


def test_missing_file_gives_a_usable_state(tmp_path):
    state = BotState.load(str(tmp_path / "nope.json"))
    assert state.start_balance is None
    assert state.halted is False
    assert state.recent_errors == []


def test_corrupt_file_does_not_stop_the_bot_but_is_recorded(tmp_path):
    """A truncated write must not be fatal -- and must not pass unnoticed either,
    because a silently blank baseline is a silently disarmed kill switch."""
    path = tmp_path / "state.json"
    path.write_text("{not json at all", encoding="utf-8")

    state = BotState.load(str(path))
    assert state.start_balance is None
    assert len(state.recent_errors) == 1
    assert "could not read" in state.recent_errors[0]["message"]


def test_unknown_fields_in_the_file_are_ignored(tmp_path):
    """So a state file written by a newer version cannot crash an older one."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"start_balance": 5000.0, "from_the_future": 1}),
                    encoding="utf-8")
    state = BotState.load(str(path))
    assert state.start_balance == 5000.0


def test_errors_are_bounded(tmp_path):
    state = BotState()
    for i in range(50):
        state.note_error("tick", f"failure {i}")
    assert len(state.recent_errors) == 20
    assert state.recent_errors[-1]["message"] == "failure 49"


def test_save_leaves_no_temporary_files_behind(tmp_path):
    """The monitor may read at any instant, so the swap has to be atomic."""
    path = str(tmp_path / "state.json")
    state = BotState()
    state.sync_baseline(10_000.0)
    state.save(path)
    state.save(path)

    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["state.json"], f"stray files: {names}"


def test_status_carries_what_a_watcher_needs(tmp_path):
    path = str(tmp_path / "status.json")
    state = BotState()
    state.sync_baseline(10_000.0)
    state.roll_day("2026-08-11", 10_000.0)
    state.note_equity(10_400.0)

    write_status(
        state, balance=10_000.0, equity=9_800.0, currency="USC", login=123456,
        dry_run=False, halt_new=False,
        open_positions=[{"symbol": "XAUUSD", "side": "buy", "lots": 0.12}],
        max_daily_loss_percent=6.0, max_total_drawdown_percent=20.0,
        path=path,
    )
    got = json.loads(open(path, encoding="utf-8").read())

    assert got["heartbeat"], "the heartbeat is the only liveness signal"
    assert got["equity"] == 9_800.0
    assert got["drawdown_percent"] == 2.0
    assert got["drawdown_limit_percent"] == 20.0
    assert got["day_loss_limit_percent"] == 6.0
    assert got["halted"] is False
    assert got["dry_run"] is False
    assert got["open_count"] == 1
    assert got["open_positions"][0]["symbol"] == "XAUUSD"
    assert got["peak_equity"] == 10_400.0
    assert got["baseline_balance"] == 10_000.0


def test_status_reports_a_halt_and_its_reason(tmp_path):
    path = str(tmp_path / "status.json")
    state = BotState()
    state.sync_baseline(10_000.0)
    state.halt("total drawdown 21.00% >= 20.00%")

    write_status(state, balance=7_900.0, equity=7_900.0, halt_new=True,
                 max_total_drawdown_percent=20.0, path=path)
    got = json.loads(open(path, encoding="utf-8").read())

    assert got["halted"] is True
    assert "21.00%" in got["halt_reason"]
    assert got["halted_at"]
    assert got["new_entries_blocked"] is True
    assert got["drawdown_percent"] == 21.0


def test_restart_count_is_visible(tmp_path):
    """A bot that has restarted forty times today is crash-looping, and the
    restart wrapper hides that completely."""
    path = str(tmp_path / "status.json")
    state = BotState()
    state.restarts = 41
    write_status(state, path=path)
    assert json.loads(open(path, encoding="utf-8").read())["restarts"] == 41



# --- reporting a position's direction ---------------------------------------
# The first version of this mapping read getattr(p, "type", 0) == 0, but
# OpenPosition has no "type" attribute -- it has "side". So the default fired
# every time and every position was reported as a buy. A real short Brent
# position was published as "side": "buy" with its stop above its entry.

class FakePosition:
    """Shaped like connectors.OpenPosition: side is +1 long, -1 short."""

    def __init__(self, side, symbol="BRENT.ecn", volume=0.04, price_open=88.5,
                 sl=92.08, tp=84.9, profit=2.4, ticket=12345):
        self.side = side
        self.symbol = symbol
        self.volume = volume
        self.price_open = price_open
        self.sl = sl
        self.tp = tp
        self.profit = profit
        self.ticket = ticket
        self.magic = 990011
        self.comment = ""


def test_a_short_is_reported_as_a_sell():
    """The reported bug. side=-1 with the stop above entry is unambiguously short."""
    from src.live.state import position_to_dict

    got = position_to_dict(FakePosition(side=-1))
    assert got["side"] == "sell"
    assert got["sl"] > got["open_price"], "a short's stop sits above its entry"
    assert got["tp"] < got["open_price"]


def test_a_long_is_reported_as_a_buy():
    from src.live.state import position_to_dict

    got = position_to_dict(FakePosition(side=1, sl=84.9, tp=92.08))
    assert got["side"] == "buy"
    assert got["sl"] < got["open_price"]


def test_an_unrecognised_side_is_not_guessed():
    """Reporting the wrong direction confidently is worse than reporting none."""
    from src.live.state import position_to_dict

    assert position_to_dict(FakePosition(side=0))["side"] == "unknown"


def test_an_object_missing_side_entirely_is_unknown_not_buy():
    """Exactly how the bug behaved: a missing attribute became a buy."""
    from src.live.state import position_to_dict

    class Bare:
        symbol = "XAUUSD.ecn"

    assert position_to_dict(Bare())["side"] == "unknown"


def test_position_fields_are_carried_through():
    from src.live.state import position_to_dict

    got = position_to_dict(FakePosition(side=-1))
    assert got["symbol"] == "BRENT.ecn"
    assert got["lots"] == 0.04
    assert got["open_price"] == 88.5
    assert got["profit"] == 2.4
    assert got["ticket"] == 12345, "the ticket makes a report traceable to MT5"


def test_profit_is_rounded_but_lots_are_not():
    from src.live.state import position_to_dict

    got = position_to_dict(FakePosition(side=1, profit=2.40567, volume=0.01))
    assert got["profit"] == 2.41
    assert got["lots"] == 0.01
