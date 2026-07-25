# MT5 Trading Bot (JustMarkets)

A Python + MetaTrader 5 multi-asset trading bot. Starts with crypto/swing trading,
designed to expand to forex, commodities, and stocks — all through a single
MetaTrader 5 (JustMarkets) account.

> **Reality check:** The goal of this bot is **positive expectancy with controlled
> drawdown**, NOT a high "win rate". A high win rate with poor risk/reward loses money.
> We optimize for: `Expectancy = (Win% x AvgWin) - (Loss% x AvgLoss) > 0`, with a
> max drawdown we can survive.

## Status / Roadmap

- [x] **Phase 1a** — Project scaffold + risk/position-sizing engine
- [x] **Phase 2**  — Strategies (trend / breakout / mean-reversion)
- [x] **Phase 4**  — Backtesting + walk-forward + expectancy/drawdown reporting
- [x] **Phase 3**  — News / economic-calendar filter (fundamentals)
- [x] **Phase 1b** — MT5 connector + live trader (Windows)  <-- WE ARE HERE
- [ ] **Phase 5**  — Demo (paper) trading run on your laptop  ← NEXT (see docs/WINDOWS_SETUP.md)
- [ ] **Phase 6**  — Small live deployment (Windows VPS + strict risk caps)

Documentation:
- **Project report:** `docs/PROJECT_REPORT.md` (architecture, results, risk, caveats)
- **Development story:** `docs/DEVELOPMENT_JOURNEY.md` (how it was built + lessons)
- **Research log:** `docs/RESEARCH_FINDINGS.md` (every experiment + verdict)
- **Run it:** `docs/WINDOWS_SETUP.md` and `docs/VPS_DEPLOYMENT.md`
- **News tools:** `docs/NEWS_TOOLS.md`

## Important environment notes

- The `MetaTrader5` Python package **only runs on Windows**. The connector layer
  (`src/connectors/`) must run on a Windows PC or Windows VPS with MT5 installed.
- Everything else (risk engine, strategy logic, backtesting) is plain Python and
  runs anywhere.
- **Always develop and test on a DEMO account first.** Never point at a live
  account until a strategy is proven in backtest AND demo.

## Cent account note

On a JustMarkets **cent account**, balance and P/L are denominated in cents
(USC). A $100 deposit shows as ~10,000. The position sizer below stays
currency-agnostic: it uses whatever `balance` and `tick_value` MetaTrader 5
reports for the account, so the math is correct for both cent and standard
accounts.

## Project layout

```
trading-bot/
├── config/
│   └── config.yaml          # risk settings, symbols, strategy params
├── src/
│   ├── risk/
│   │   └── position_sizing.py   # <-- built now: lot sizing from risk %
│   ├── connectors/          # (next) MT5 wrapper - runs on Windows
│   ├── strategy/            # (later) technical strategies
│   ├── news/                # (later) economic calendar filter
│   └── backtest/            # (later) backtesting + reporting
└── tests/
    └── test_position_sizing.py
```

## Setup (later, on Windows for live/demo)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
