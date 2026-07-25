# Development Journey

How this bot went from a one-line idea to a validated, 24/7-deployed system —
and the lessons learned along the way. Written as a plain-language story of the
build.

---

## Where it started

The idea: a hedging/trading bot for forex, crypto, and commodities that trades
autonomously (lot size, risk %, SL/TP), reacts to news, and combines technicals
with fundamentals — targeting a **70–80% win rate**.

The very first thing we did was **reframe the goal.** A high win rate is one of
the most misleading metrics in trading — you can win 80% of trades and still lose
money if the losses are big. The real target became **positive expectancy with
controlled drawdown**. Everything after that followed from this honesty.

## The build, phase by phase

**1. Foundations & the risk engine.** Before any strategy, we built the survival
layer: currency-agnostic position sizing (risk % → lot size from the stop
distance and the broker's real specs) with hard safety caps. Tested first.

**2. Data + first strategy + an honest backtester.** Pulled real market data,
built an EMA+RSI swing strategy, and — crucially — an event-driven backtester
with **no look-ahead** and realistic costs. The first strategy was break-even.
That was the point: the backtester tells the truth.

**3. Edge hunting.** Adding a **higher-timeframe trend filter** turned break-even
into a real edge. We compared trend vs breakout vs mean-reversion, then ran
**walk-forward validation** (optimize on the past, test on unseen data). The edge
held out-of-sample — not curve-fitting.

**4. Multi-asset expansion.** Moved beyond crypto to forex and commodities. Key
discovery: **different markets have different character.** Trend-following shines
on commodities and crypto; range-bound FX majors prefer **mean-reversion**. Using
the wrong tool turned winners into losers.

**5. The news layer.** Built an economic-calendar blackout so the bot avoids
trading into high-impact events (NFP/CPI/FOMC). Honest finding: as a *price*
signal it was neutral, but as a *risk filter* it's valuable (real news-time
spreads blow out in ways backtests can't see).

**6. Going live (on demo).** Built the MetaTrader 5 connector and a live
orchestrator with dry-run mode and kill switches. Validated the full order
pathway on a JustMarkets demo account — connection, sizing with real specs,
order placement with SL/TP, and clean closes.

**7. Performance logging + 24/7.** Added a trade/equity journal, a live
performance report, and a Windows-VPS deployment guide with auto-restart so the
bot runs without the laptop being on.

**8. Mining a 344-indicator repo (SMC/ICT).** Catalogued a big pack of TradingView
"Smart Money Concepts" indicators and translated the best ideas — Fair Value
Gaps, Order Blocks, Liquidity Sweeps — into strategies. **Most failed
out-of-sample.** A Fair Value Gap edge on BTC that looked great in-sample (+27%)
collapsed to −12% out-of-sample — a textbook overfitting trap, caught before any
money was risked. Only a silver Order-Block candidate survived (flagged for demo).

**9. Evidence-based enhancements.** Instead of chasing more indicators, we
researched what actually has academic backing — momentum/trend-following,
diversification, and **volatility targeting** — and added them. Vol targeting
helped mean-reversion and hurt trend (it trims trend's tail winners), so we
applied it selectively.

**10. Expanding the universe.** Scanned 25 instruments (FX, commodities, indices,
crypto). Nine passed walk-forward; the portfolio grew from 4 to 8 slots.
Blending the uncorrelated edges more than doubled the risk-adjusted return —
diversification, the "only free lunch," demonstrated on our own numbers.

**11. News awareness tools.** Added a calendar report and a news-sentiment
dashboard (forex + geopolitics like the Strait of Hormuz, Fed, oil). These inform
the *human* — they are deliberately **not** wired to auto-trading, because
sentiment→trade is unbacktestable and too slow to beat institutions.

**12. Consolidation.** Merged everything to `main`, and decoupled the personal
live config from git so updates never conflict.

## The lessons that kept repeating

1. **Win rate is a vanity metric.** Expectancy and risk/reward are what pay.
2. **Backtest everything; trust only out-of-sample.** In-sample results lie.
3. **Match the strategy to the market's character** (trend vs range).
4. **Edges come from mechanisms, not secret indicators.** The flashy SMC/ICT
   tools mostly failed; boring, evidence-based methods (trend, vol targeting,
   diversification) delivered.
5. **Risk management is the product.** Sizing, stops, caps, kill switches, and
   news blackout matter more than any entry signal.
6. **Diversification is the closest thing to a free lunch.**
7. **Don't automate what you can't validate** (news-sentiment auto-trading).

## Where it ended up

A complete, validated, multi-asset systematic trading system:
- 8-instrument diversified portfolio (trend + mean-reversion), vol-targeting
  applied selectively, news-aware risk layer.
- Live-proven on a JustMarkets demo account, deployed 24/7 on a Windows VPS.
- 31 automated tests, full documentation, everything consolidated on `main`.

**Status:** running on **demo**. The plan is to forward-test for 1–3 months,
review the live numbers, and only then consider real capital — small, with tight
risk. Built patiently, honestly, one validated step at a time.

> Reminder: trading involves real risk of loss. This is a research/education
> project, not financial advice.
