"""
Live/demo trading orchestrator.

Ties everything together and runs the loop on your Windows laptop:
  connect -> for each instrument: fetch closed candles -> signals -> news
  blackout -> risk-size with REAL broker specs -> decide -> execute.

Safety first:
  * dry_run: logs intended actions, sends NO orders (default; use it first).
  * Kill switch on total drawdown; daily-loss limit halts NEW entries.
  * max_open_trades cap; every order tagged with a magic number.
  * Acts only on CLOSED bars (drops the still-forming bar) - no repainting.

Run on Windows:  python live_trader.py
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

import pandas as pd
import yaml

from ..connectors import MT5Connector
from ..risk.position_sizing import RiskParams, MinLotPolicy
from ..risk.vol_target import volatility_target_scalar
from ..news.calendar import ForexFactoryCalendar
from ..news.filter import NewsFilter
from .portfolio import DEFAULT_PORTFOLIO, PortfolioSlot
from .decision import decide
from .journal import CSVJournal
from .lock import AlreadyRunning, SingleInstance
from .state import BotState, position_to_dict, write_status

log = logging.getLogger("trader")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

_TF_MINUTES = {"M15": 15, "H1": 60, "H4": 240, "D1": 1440}


@dataclass
class TraderConfig:
    dry_run: bool
    symbols: dict            # logical -> broker symbol
    risk: RiskParams
    max_open_trades: int
    max_daily_loss_percent: float
    max_total_drawdown_percent: float
    news_enabled: bool
    news_before: int
    news_after: int
    magic: int
    poll_seconds: int
    lookback: int
    conn: dict

    @staticmethod
    def load(path: str) -> "TraderConfig":
        with open(path) as f:
            c = yaml.safe_load(f)
        r = c["risk"]
        return TraderConfig(
            dry_run=c.get("dry_run", True),
            symbols=c["symbols"],
            risk=RiskParams(
                risk_percent_per_trade=r["risk_percent_per_trade"],
                max_risk_percent_per_trade=r["max_risk_percent_per_trade"],
                on_min_lot_exceeds_risk=MinLotPolicy.SKIP,
            ),
            max_open_trades=r["max_open_trades"],
            max_daily_loss_percent=r["max_daily_loss_percent"],
            max_total_drawdown_percent=r["max_total_drawdown_percent"],
            news_enabled=c["news_filter"]["enabled"],
            news_before=c["news_filter"]["before_minutes"],
            news_after=c["news_filter"]["after_minutes"],
            magic=c["run"]["magic_number"],
            poll_seconds=c["run"]["poll_seconds"],
            lookback=c["run"]["candles_lookback"],
            conn=c.get("connection", {}) or {},
        )


class LiveTrader:
    def __init__(self, cfg: TraderConfig, portfolio: list[PortfolioSlot] | None = None):
        self.cfg = cfg
        self.portfolio = portfolio or DEFAULT_PORTFOLIO
        self.conn = MT5Connector(magic=cfg.magic)
        self.journal = CSVJournal()
        self._raw_events: list = []
        self._filter_cache: dict = {}
        self._news_day = None
        self._last_bar: dict[str, pd.Timestamp] = {}
        # Safety state lives on disk, so a crash and restart cannot forgive a
        # drawdown that already happened. See state.py for why that matters.
        self.state = BotState.load()

    # ---- news ----
    def _refresh_news(self) -> None:
        today = datetime.now(timezone.utc).date()
        if self._news_day == today and self._raw_events:
            return
        cal = ForexFactoryCalendar()
        events = []
        # Fetch each week independently so one missing feed (404) doesn't wipe
        # out the others. In practice only "thisweek" is reliably published.
        for wk in ("lastweek", "thisweek", "nextweek"):
            try:
                events.extend(cal.events(week=wk, min_impact="High"))
            except Exception as e:
                log.debug("news feed '%s' unavailable: %s", wk, e)
        self._raw_events = events
        self._filter_cache = {}   # invalidate per-currency filters
        self._news_day = today
        if events:
            log.info("Refreshed news calendar: %d high-impact events this week", len(events))
        else:
            log.warning("No news events fetched; proceeding without blackout.")

    def _in_blackout(self, currencies: set[str]) -> bool:
        """Blackout scoped to the instrument's relevant currencies only."""
        if not self.cfg.news_enabled:
            return False
        key = frozenset(currencies)
        nf = self._filter_cache.get(key)
        if nf is None:
            nf = NewsFilter(self._raw_events, self.cfg.news_before,
                            self.cfg.news_after, currencies=set(currencies))
            self._filter_cache[key] = nf
        return nf.is_blackout(pd.Timestamp.now(tz="UTC"))

    # ---- safety ----
    def _check_kill_switches(self, equity: float) -> bool:
        """Return True if trading should be HALTED (no new entries).

        The baseline comes from persisted state rather than from the balance at
        connect time, which is what makes the switch survive a restart. Messages
        are emitted once per event, not once per poll: at sixty-second intervals
        the old code wrote the same halt line fourteen hundred times a day.
        """
        self.state.note_equity(equity)

        dd = self.state.drawdown_percent(equity)
        if dd >= self.cfg.max_total_drawdown_percent:
            reason = (f"total drawdown {dd:.2f}% >= "
                      f"{self.cfg.max_total_drawdown_percent:.2f}%")
            if self.state.halt(reason):
                log.error("KILL SWITCH: %s. Halting.", reason)
                self._record_event("kill_switch", reason, equity)
            self._save_state()
            return True

        today = datetime.now(timezone.utc).date().isoformat()
        if self.state.roll_day(today, equity):
            self._save_state()

        day_dd = self.state.day_drawdown_percent(equity)
        if day_dd >= self.cfg.max_daily_loss_percent:
            reason = (f"daily loss {day_dd:.2f}% >= "
                      f"{self.cfg.max_daily_loss_percent:.2f}%")
            if self.state.halt_day(reason):
                log.warning("%s. No new entries today.", reason)
                self._record_event("daily_loss_halt", reason, equity)
                self._save_state()
            return True

        return self.state.halted

    def _publish_status(self, acct, halt_new: bool, open_bot) -> None:
        """Rewrite logs/status.json so something outside can see how we are doing.

        The heartbeat is the point. Nothing else can tell a watcher on another
        machine that the process has stopped: a bot that has died looks exactly
        like a bot that has found nothing to trade, unless the timestamp is
        going stale.
        """
        try:
            positions = [position_to_dict(p) for p in (open_bot or [])]
            write_status(
                self.state,
                balance=acct.balance, equity=acct.equity,
                currency=getattr(acct, "currency", ""),
                login=getattr(acct, "login", ""),
                dry_run=self.cfg.dry_run,
                halt_new=halt_new,
                open_positions=positions,
                max_daily_loss_percent=self.cfg.max_daily_loss_percent,
                max_total_drawdown_percent=self.cfg.max_total_drawdown_percent,
            )
        except Exception as exc:
            # Monitoring must never be able to stop the thing it monitors.
            log.debug("status write failed: %s", exc)

    def _save_state(self) -> None:
        """Persist safety state. A failure here must never stop the bot."""
        try:
            self.state.save()
        except Exception as exc:
            log.warning("could not save state: %s", exc)

    def _record_event(self, event: str, reason: str, equity: float) -> None:
        try:
            self.journal.log_event(event, reason=reason, equity=equity)
        except Exception as exc:
            log.debug("journal event write failed: %s", exc)

    # ---- main ----
    def start(self) -> None:
        c = self.cfg.conn
        acct = self.conn.connect(
            login=c.get("login") or None,
            password=c.get("password") or None,
            server=c.get("server") or None,
            path=c.get("path") or None,
        )
        self._on_connect(acct, loop=True)
        try:
            while True:
                self._tick()
                time.sleep(self.cfg.poll_seconds)
        except KeyboardInterrupt:
            log.info("Stopped by user.")
        finally:
            self.conn.shutdown()

    def run_once(self) -> None:
        """Connect, evaluate every instrument ONCE, log decisions, disconnect.

        A fast, safe validation tool - shows what the bot would do right now
        without committing to the long-running loop.
        """
        c = self.cfg.conn
        acct = self.conn.connect(
            login=c.get("login") or None,
            password=c.get("password") or None,
            server=c.get("server") or None,
            path=c.get("path") or None,
        )
        self._on_connect(acct, loop=False)
        try:
            self._tick()
        finally:
            self.conn.shutdown()
        log.info("One-shot check complete.")

    def _on_connect(self, acct, loop: bool) -> None:
        """Announce the connection and reconcile the persisted baseline.

        Counting restarts is not bookkeeping for its own sake: a bot that has
        restarted forty times in a day is crash-looping, and before this the
        restart wrapper hid that completely.
        """
        self.state.sync_baseline(acct.balance)
        if loop:
            if self.state.started_at:
                self.state.restarts += 1
            self.state.started_at = self.state.started_at or _utc_now()
        self._save_state()

        log.info("Connected. Login %s  Balance %.2f %s  %s",
                 acct.login, acct.balance, acct.currency,
                 "[DRY RUN]" if self.cfg.dry_run else "[LIVE ORDERS]")
        log.info("Kill-switch baseline %.2f (persisted); drawdown now %.2f%% "
                 "of %.2f%% limit.",
                 self.state.start_balance or 0.0,
                 self.state.drawdown_percent(acct.equity),
                 self.cfg.max_total_drawdown_percent)
        if self.state.halted:
            # The most important line the bot can print. Previously a halt did
            # not survive a restart at all, so this state was unreachable.
            log.error("STILL HALTED from a previous run (%s at %s). No new "
                      "entries will be taken. Delete logs/state.json to clear.",
                      self.state.halt_reason, self.state.halted_at)
        if loop:
            self._record_event("start", f"restart #{self.state.restarts}"
                               if self.state.restarts else "first start",
                               acct.equity)

    def _tick(self) -> None:
        self._refresh_news()
        acct = self.conn.account_info()
        try:
            self.journal.log_equity(acct.balance, acct.equity)
        except Exception as e:
            log.debug("journal equity write failed: %s", e)
        halt_new = self._check_kill_switches(acct.equity)
        open_bot = self.conn.bot_positions()
        open_count = len(open_bot)
        self._publish_status(acct, halt_new, open_bot)

        for slot in self.portfolio:
            broker_symbol = self.cfg.symbols.get(slot.logical)
            if not broker_symbol:
                continue
            try:
                self._process_slot(slot, broker_symbol, acct, halt_new, open_count)
            except Exception as e:
                log.exception("Error processing %s (%s): %s", slot.logical, broker_symbol, e)

    def _process_slot(self, slot, symbol, acct, halt_new, open_count) -> None:
        df = self.conn.get_candles(symbol, slot.timeframe, self.cfg.lookback)
        if len(df) < 60:
            return
        closed = df.iloc[:-1]  # drop the still-forming bar
        latest_time = closed.index[-1]

        # Only act once per newly-closed bar.
        if self._last_bar.get(symbol) == latest_time:
            return
        self._last_bar[symbol] = latest_time

        strat = slot.build()
        signals = strat.generate_signals(closed)

        positions = self.conn.bot_positions(symbol)
        pos_side = positions[0].side if positions else 0
        spec = self.conn.symbol_spec(symbol)
        bid, ask = self.conn.current_tick(symbol)
        blackout = self._in_blackout(slot.news_currencies)

        # Volatility-targeting scalar (only for slots configured to use it).
        risk_scalar = 1.0
        if getattr(slot, "use_vol_target", False):
            vs = volatility_target_scalar(closed["close"], lookback=14,
                                          median_window=500, min_scale=0.5, max_scale=1.5)
            if len(vs):
                risk_scalar = float(vs[-1])

        last = signals.iloc[-1]
        log.info(
            "[%s/%s] bar=%s close=%.5f signal=%+d position=%+d  volscale=%.2f%s",
            slot.logical, symbol, str(latest_time), float(last["close"]),
            int(last["signal"]), pos_side, risk_scalar,
            "  [NEWS BLACKOUT]" if blackout else "",
        )

        d = decide(
            signals=signals, position_side=pos_side, bid=bid, ask=ask,
            balance=acct.balance, spec=spec, risk=self.cfg.risk,
            sl_atr_mult=strat.sl_atr_mult, tp_rr=strat.tp_rr, blackout=blackout,
            risk_scalar=risk_scalar,
        )

        # Entry gating by portfolio-level limits.
        if d.action == "enter":
            if halt_new:
                log.info("[%s] entry suppressed (risk halt).", slot.logical)
                return
            if open_count >= self.cfg.max_open_trades:
                log.info("[%s] entry suppressed (max_open_trades=%d).",
                         slot.logical, self.cfg.max_open_trades)
                return

        self._execute(slot, symbol, d, positions)

    def _execute(self, slot, symbol, d, positions) -> None:
        tag = f"[{slot.logical}/{symbol}]"
        if d.action in ("nothing", "hold"):
            log.info("%s -> %s (%s)", tag, d.action, d.reason)
            return

        if d.action == "skip":
            log.info("%s SKIP: %s", tag, d.reason)
            self._journal(slot.logical, "skip", d, reason=d.reason)
            return

        if d.action == "enter":
            log.info("%s ENTER %s %.4f lots  SL=%.5f TP=%.5f  (%s)",
                     tag, "BUY" if d.side == 1 else "SELL", d.lots, d.sl, d.tp, d.reason)
            if self.cfg.dry_run:
                log.info("%s [DRY RUN] order not sent.", tag)
                self._journal(slot.logical, "enter_dryrun", d)
                return
            res = self.conn.place_market_order(symbol, d.side, d.lots, d.sl, d.tp,
                                               comment=slot.logical)
            log.info("%s order result: %s", tag, res)
            self._journal(slot.logical, "enter", d, retcode=res.get("retcode"))

        elif d.action == "close":
            log.info("%s CLOSE position (%s)", tag, d.reason)
            if self.cfg.dry_run:
                log.info("%s [DRY RUN] close not sent.", tag)
                self._journal(slot.logical, "close_dryrun", d, reason=d.reason)
                return
            for p in positions:
                res = self.conn.close_position(p)
                log.info("%s close result: %s", tag, res)
                self._journal(slot.logical, "close", d, retcode=res.get("retcode"),
                              reason=d.reason)

    def _journal(self, symbol, action, d, retcode="", reason="") -> None:
        try:
            self.journal.log_action(
                symbol=symbol, action=action, side=d.side, lots=d.lots,
                sl=d.sl, tp=d.tp, retcode=retcode or "", reason=reason or d.reason,
            )
        except Exception as e:
            log.debug("journal action write failed: %s", e)


def _setup_logging(path: str = "logs/bot.log") -> None:
    """Log to the console and to a rotating file.

    Console-only logging meant every error the bot produced was lost. run_bot.bat
    does not redirect output, and it restarts the process thirty seconds after any
    exit -- so a traceback, an MT5 "initialize failed", or the kill-switch message
    itself would scroll away and leave no evidence that anything had happened.

    Five files of two megabytes is a few weeks of history at this log level, and
    is bounded so an unattended VPS cannot fill its disk.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        handlers.append(
            RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5,
                                encoding="utf-8")
        )
    except Exception as exc:  # a read-only disk must not stop the bot
        print(f"WARNING: file logging unavailable ({exc}); console only.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def run(config_path: str = "config/live_config.yaml") -> None:
    _setup_logging()
    # Refuse to be the second bot on this account. Two instances each keep their
    # own drawdown baseline in memory, which splits the kill switch in half so
    # neither side sees the whole loss.
    try:
        SingleInstance().acquire()
    except AlreadyRunning as exc:
        log.error("Not starting: %s", exc)
        raise SystemExit(1)
    cfg = TraderConfig.load(config_path)
    LiveTrader(cfg).start()


def run_once(config_path: str = "config/live_config.yaml") -> None:
    _setup_logging()
    cfg = TraderConfig.load(config_path)
    LiveTrader(cfg).run_once()
