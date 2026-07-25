# Trading Bot — Project Report

A multi-asset, systematic algorithmic trading bot for MetaTrader 5 (JustMarkets),
built and validated the disciplined way: every automated decision is backtested,
and every claim is checked out-of-sample.

> ⚠️ **Disclaimer.** This software is for research and education. Trading carries
> substantial risk of loss. Nothing here is financial advice. All results below
> are **backtests / out-of-sample simulations**, not live returns — past
> performance does not predict the future. Run on a **demo account** first and
> only risk capital you can afford to lose.

---

## 1. Objective

Build a bot that trades forex, commodities (and optionally crypto) autonomously,
with automated position sizing, stop-loss/take-profit, and a news-aware risk
layer.

**Important reframing:** the original goal was a "70–80% win rate." Early on we
established (and later confirmed with our own data and independent research) that
**win rate is misleading** — a strategy can win 40% of the time and be very
profitable if winners outsize losers. The real objective became **positive
expectancy with controlled drawdown**, judged out-of-sample.

## 2. System architecture

```
Data sources ─┐
  OKX (crypto) │   ┌────────────┐   ┌──────────────┐   ┌───────────────┐
  Yahoo (FX/   ├──▶│  Strategy  │──▶│  Risk engine  │──▶│ MT5 connector │──▶ Broker
  commodities/ │   │  signals   │   │ (sizing, vol  │   │ (orders, SL/TP│    (demo)
  indices)     │   └────────────┘   │  target, caps)│   │  positions)   │
News/calendar ─┘         ▲          └──────────────┘   └───────────────┘
  (ForexFactory)         │ news blackout filter
```

Key modules (`src/`):
- `risk/` — currency-agnostic position sizing, hard caps, volatility targeting
- `strategy/` — trend, mean-reversion, breakout, FVG, order-block, liquidity-sweep
- `backtest/` — event-driven engine (no look-ahead) + walk-forward + metrics
- `data/` — OKX and Yahoo loaders
- `news/` — economic calendar, blackout filter, sentiment scorer
- `connectors/` — MetaTrader 5 wrapper (Windows)
- `live/` — decision logic, portfolio definition, live orchestrator, journal

## 3. Validation methodology (the core discipline)

- **Walk-forward analysis:** parameters are optimized on past data, then measured
  on the *next unseen* window, rolled forward. This is the honest test that
  separates a real edge from curve-fitting.
- **Expectancy over win rate:** we optimize for average profit per trade (in "R")
  and risk-adjusted return (Sharpe), not accuracy.
- **Honest cost modelling:** spread/slippage applied to every fill; conservative
  worst-case fills; no look-ahead (signals on bar close, entry next bar open).
- **Reject aggressively:** most ideas were discarded (see §7). Surviving an
  out-of-sample walk-forward is the bar for inclusion.

## 4. Strategies

| Strategy | Type | Notes |
|---|---|---|
| EMA + RSI + higher-timeframe filter | Trend-following | Core edge on trending markets |
| Bollinger + RSI | Mean-reversion | For range-bound FX; vol-targeting ON |
| Donchian breakout | Breakout | Tested, not selected |
| Fair Value Gap (FVG) | SMC structure | Tested, **rejected** |
| Order Block | SMC structure | Rejected except a silver candidate |
| Liquidity Sweep | ICT reversal | Tested, **rejected** |

## 5. The validated portfolio

From a 25-instrument universe scan, 9 passed walk-forward; 8 non-crypto form the
default portfolio (BTC optional per user preference). Volatility targeting is
applied ON for mean-reversion, OFF for trend (see §6).

| Instrument | Strategy | Vol-target |
|---|---|---|
| Gold (XAUUSD) | Trend | off |
| Silver (XAGUSD) | Trend | off |
| Natural Gas | Trend | off |
| Platinum | Trend | off |
| GBPJPY | Trend | off |
| AUDUSD | Mean-reversion | on |
| USDJPY | Mean-reversion | on |
| Brent | Mean-reversion | on |
| *(optional)* BTC | Trend | off |

**Out-of-sample results (walk-forward)** — indicative, see caveats in §8:

| Instrument | Strategy | Sharpe | Return | Max DD |
|---|---|---|---|---|
| Gold | trend | 2.16* | +36.4% | 10.7% |
| AUDUSD | mean-rev | 1.63 | +29.7% | 8.9% |
| Silver | trend | 1.42 | +19.9% | 6.9% |
| NatGas | trend | 1.20 | +22.2% | 6.4% |
| BTC | trend | 0.92 | +24.6% | 10.1% |
| Platinum | trend | 0.74 | +7.9% | 6.7% |
| Brent | mean-rev | 0.73 | +11.2% | 9.1% |
| GBPJPY | trend | 0.67 | +12.8% | 11.5% |
| USDJPY | mean-rev | 0.64 | +8.4% | 11.4% |

\* Gold's figure is inflated by an exceptional 2024–26 bull run; do not
extrapolate.

**Diversification:** equal-weighting the edges lifted the blended Sharpe well
above the ~1.0 average of individual edges and sharply reduced drawdown — the
"only free lunch" in action (exact figure is optimistic; see §8).

## 6. Risk management

- **Position sizing:** risk a fixed % of equity per trade; lot size derived from
  the ATR-based stop distance and the broker's real contract specs
  (currency-agnostic — works on cent and standard accounts).
- **Volatility targeting:** scales risk down in high-vol regimes / up in calm
  ones. Applied selectively — it *helps* mean-reversion but *hurts* trend
  (it cuts trend's skew-driven tail winners), so ON for MR only.
- **Hard caps:** max risk % per trade, max open trades, **daily-loss halt**, and
  a **total-drawdown kill switch**.
- **News blackout:** no new entries around high-impact events (protects against
  news-time spread blowouts and gaps).
- **Broker-side SL/TP:** every trade carries a stop and target at the broker, so
  risk is capped even if the bot is offline.

## 7. What we tested and REJECTED (discipline in action)

- **Fair Value Gap, Liquidity Sweep** — failed out-of-sample.
- **Order Blocks** — rejected except a silver candidate flagged for demo A/B.
- **Indices (S&P/Nasdaq/Dow/DAX)** — did not pass on the tested window.
- **News-sentiment auto-trading** — deliberately NOT built: unbacktestable and
  latency-disadvantaged. News is used only as a risk filter + an informational
  dashboard for the human.
- **SMC/ICT indicators generally** — independent research and our own tests agree
  they lack verified edge; used only as an idea source.

## 8. Limitations & honest caveats

- **Backtests, not live results.** Forward performance will differ and be lower.
- **Short intraday history.** Yahoo H4 data spans ~2 years; regime coverage is
  limited. Some edges may be period-specific (e.g., the gold bull run).
- **Multiple-comparisons risk.** Many combinations were tested; some "keepers"
  near the threshold could be partly luck. Demo forward-testing is the arbiter.
- **Diversification blend is optimistic** (selection bias, correlated
  commodities, flat-day volatility dilution). Expect a real but smaller benefit.
- **Costs.** Real spreads/commissions/slippage — especially around news — can be
  worse than modelled.

## 9. Deployment & testing

- **MT5 connector** validated live on a JustMarkets ECN **demo** account
  (order placement, SL/TP, filling mode, close — all confirmed).
- **24/7** via Windows VPS with auto-restart and boot autostart.
- **Monitoring:** `scripts/report.py` (live P&L vs backtest), calendar report and
  news dashboard for awareness.
- **31 automated tests** covering risk sizing, news filter, decision logic,
  volatility targeting, and sentiment scoring.

## 10. Roadmap

- Forward-test on demo for 1–3 months; review with `report.py`.
- Quarterly parameter re-optimization (walk-forward refresh).
- A/B test the silver Order-Block candidate vs the trend version.
- Optional: cross-sectional momentum ranking across the universe.

---

*See `docs/RESEARCH_FINDINGS.md` for the full experiment log, `docs/WINDOWS_SETUP.md`
and `docs/VPS_DEPLOYMENT.md` for running it, and `docs/NEWS_TOOLS.md` for the
awareness tools.*
