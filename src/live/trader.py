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
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
import yaml

from ..connectors import MT5Connector
from ..risk.position_sizing import RiskParams, MinLotPolicy
from ..news.calendar import ForexFactoryCalendar
from ..news.filter import NewsFilter
from .portfolio import DEFAULT_PORTFOLIO, PortfolioSlot
from .decision import decide

log = logging.getLogger("trader")

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
        self._news: NewsFilter | None = None
        self._news_day = None
        self._last_bar: dict[str, pd.Timestamp] = {}
        self._start_balance: float | None = None
        self._day = None
        self._day_start_equity: float | None = None
        self._halted = False

    # ---- news ----
    def _refresh_news(self) -> None:
        today = datetime.now(timezone.utc).date()
        if self._news is not None and self._news_day == today:
            return
        try:
            cal = ForexFactoryCalendar()
            events = []
            for wk in ("lastweek", "thisweek", "nextweek"):
                events.extend(cal.events(week=wk, min_impact="High"))
            self._news = NewsFilter(events, self.cfg.news_before, self.cfg.news_after)
            self._news_day = today
            log.info("Refreshed news calendar: %d high-impact events", len(events))
        except Exception as e:
            log.warning("Could not refresh news (%s); proceeding without blackout", e)
            self._news = NewsFilter([], self.cfg.news_before, self.cfg.news_after)
            self._news_day = today

    def _in_blackout(self, currencies: set[str]) -> bool:
        if not self.cfg.news_enabled or self._news is None:
            return False
        # Build a currency-scoped view lazily is overkill; reuse filter but the
        # stored events already include all currencies, so scope here:
        now = pd.Timestamp.now(tz="UTC")
        # NewsFilter stores all currencies; approximate by checking the global
        # filter (dominant driver USD). For per-currency precision we could keep
        # separate filters; USD covers our portfolio's main risk.
        return self._news.is_blackout(now)

    # ---- safety ----
    def _check_kill_switches(self, equity: float) -> bool:
        """Return True if trading should be HALTED (no new entries)."""
        if self._start_balance:
            dd = (self._start_balance - equity) / self._start_balance * 100
            if dd >= self.cfg.max_total_drawdown_percent:
                log.error("KILL SWITCH: total drawdown %.2f%% >= %.2f%%. Halting.",
                          dd, self.cfg.max_total_drawdown_percent)
                self._halted = True
                return True

        today = datetime.now(timezone.utc).date()
        if self._day != today:
            self._day = today
            self._day_start_equity = equity
        if self._day_start_equity:
            day_dd = (self._day_start_equity - equity) / self._day_start_equity * 100
            if day_dd >= self.cfg.max_daily_loss_percent:
                log.warning("Daily loss %.2f%% >= %.2f%%. No new entries today.",
                            day_dd, self.cfg.max_daily_loss_percent)
                return True
        return False

    # ---- main ----
    def start(self) -> None:
        c = self.cfg.conn
        acct = self.conn.connect(
            login=c.get("login") or None,
            password=c.get("password") or None,
            server=c.get("server") or None,
            path=c.get("path") or None,
        )
        self._start_balance = acct.balance
        log.info("Connected. Login %s  Balance %.2f %s  %s",
                 acct.login, acct.balance, acct.currency,
                 "[DRY RUN]" if self.cfg.dry_run else "[LIVE ORDERS]")
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
        self._start_balance = acct.balance
        log.info("Connected. Login %s  Balance %.2f %s  %s",
                 acct.login, acct.balance, acct.currency,
                 "[DRY RUN]" if self.cfg.dry_run else "[LIVE ORDERS]")
        try:
            self._tick()
        finally:
            self.conn.shutdown()
        log.info("One-shot check complete.")

    def _tick(self) -> None:
        self._refresh_news()
        acct = self.conn.account_info()
        halt_new = self._check_kill_switches(acct.equity) or self._halted
        open_bot = self.conn.bot_positions()
        open_count = len(open_bot)

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

        d = decide(
            signals=signals, position_side=pos_side, bid=bid, ask=ask,
            balance=acct.balance, spec=spec, risk=self.cfg.risk,
            sl_atr_mult=strat.sl_atr_mult, tp_rr=strat.tp_rr, blackout=blackout,
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
            log.debug("%s %s (%s)", tag, d.action, d.reason)
            return

        if d.action == "skip":
            log.info("%s SKIP: %s", tag, d.reason)
            return

        if d.action == "enter":
            log.info("%s ENTER %s %.4f lots  SL=%.5f TP=%.5f  (%s)",
                     tag, "BUY" if d.side == 1 else "SELL", d.lots, d.sl, d.tp, d.reason)
            if self.cfg.dry_run:
                log.info("%s [DRY RUN] order not sent.", tag)
                return
            res = self.conn.place_market_order(symbol, d.side, d.lots, d.sl, d.tp,
                                               comment=slot.logical)
            log.info("%s order result: %s", tag, res)

        elif d.action == "close":
            log.info("%s CLOSE position (%s)", tag, d.reason)
            if self.cfg.dry_run:
                log.info("%s [DRY RUN] close not sent.", tag)
                return
            for p in positions:
                res = self.conn.close_position(p)
                log.info("%s close result: %s", tag, res)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run(config_path: str = "config/live_config.yaml") -> None:
    _setup_logging()
    cfg = TraderConfig.load(config_path)
    LiveTrader(cfg).start()


def run_once(config_path: str = "config/live_config.yaml") -> None:
    _setup_logging()
    cfg = TraderConfig.load(config_path)
    LiveTrader(cfg).run_once()
