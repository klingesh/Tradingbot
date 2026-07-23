# Research Findings — Edge Hunt Across Crypto, Forex & Commodities

All numbers below are **out-of-sample (OOS)** from walk-forward analysis:
parameters were optimized on past data, then measured on the *next* unseen
window, rolled forward. This is the honest test of whether an edge is real
rather than curve-fit.

Position sizing risks 2% per trade. Returns/drawdown are scale-invariant
(reported as %) so they reflect the strategy, not contract size. Costs
(spread/slippage) are modeled on every fill.

## The one principle that runs through everything

**Win rate is not the goal — positive expectancy is.** Repeatedly, the
highest-win-rate setups were among the *worst* performers, and profitable
strategies won only ~40–55% of the time but with winners larger than losers.

## Validated edges (keep these)

| Instrument | Class | Timeframe | Strategy | PF | Return | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| BTCUSD | crypto | H4 | Trend (EMA+RSI + daily filter) | 1.39 | +22.8% | 12.7% | 0.84 |
| XAUUSD (gold) | commodity | H4 | Trend (EMA+RSI + daily filter) | 1.87 | +13.9% | 5.9% | **1.35** |
| AUDUSD | forex | H4 | Mean-reversion (Bollinger+RSI) | 1.60 | +18.9% | 9.1% | **1.27** |
| USDJPY | forex | H4 | Mean-reversion (Bollinger+RSI) | 1.76 | +17.9% | 11.9% | 1.18 |
| XAGUSD (silver) | commodity | H4 | Trend (EMA+RSI + daily filter) | 1.61 | +11.0% | 6.9% | 0.85 |
| GBPUSD | forex | Daily | Trend (EMA+RSI + weekly filter) | 1.45 | +11.5% | 8.3% | 0.27 |

## Avoid (no edge found with either approach)

| Instrument | Notes |
|---|---|
| EURUSD | Loses with both trend and mean-reversion at H4. Too efficient/noisy. |
| USDCAD | Marginal on daily trend; mean-reversion loses badly. Skip for now. |
| WTI (oil) | Only marginally positive at H4; trends better on daily. Low priority. |

## Key insights

1. **Match the strategy to the instrument's character.**
   - *Trending* markets (crypto, gold, silver) → **trend-following**.
   - *Range-bound* majors (AUDUSD, USDJPY) → **mean-reversion**.
   - Using the wrong tool turns a winner into a loser (e.g. USDJPY: −8% trend vs
     +18% mean-reversion).

2. **Timeframe matters.** Forex majors whipsaw on H4 for trend-following but the
   H4 mean-reversion edge is strong. Commodities trend well even on H4.

3. **Crypto has the strongest raw trend edge** but the highest volatility. Gold
   gave the best *risk-adjusted* result (Sharpe 1.35) with a tiny 5.9% drawdown.

4. **A diversified portfolio beats any single bet.** These edges come from
   different asset classes and different strategy types, so their ups and downs
   are unlikely to line up — combining them should smooth the equity curve.

## Honest caveats

- We tested ~16 instrument/strategy combinations. With that many tries, a few
  winners could be partly luck (selection bias). The remedy: **forward-test the
  finalists on a demo account** and keep monitoring OOS behavior.
- H4 forex history is only ~2 years (Yahoo hourly limit) → fewer trades, lower
  statistical confidence than the crypto/daily sets.
- Modeled spreads may be tighter than real JustMarkets fills. Demo validates this.
- No news/fundamentals filter yet.

## Recommended portfolio (starting point)

A small basket of the strongest, logically-sound validated edges:

| Slot | Instrument | Strategy |
|---|---|---|
| 1 | XAUUSD (gold) | H4 trend-following |
| 2 | AUDUSD | H4 mean-reversion |
| 3 | USDJPY | H4 mean-reversion |
| 4 | XAGUSD (silver) | H4 trend-following |
| (opt) | BTCUSD | H4 trend-following (if crypto risk acceptable) |

Next steps: news/economic-calendar filter → MT5 connector → demo forward-test.


---

## News / economic-calendar filter (fundamentals layer)

We added a high-impact event calendar (NFP always the first Friday; FOMC on
published dates) and an **avoid-mode** filter that blocks new entries in a
window around events. Tested on the recommended portfolio, with vs without:

| Instrument | Filter | PF | Return | Sharpe |
|---|---|---|---|---|
| Gold | off / on | 1.87 / 1.86 | +13.90% / +13.85% | 1.35 / 1.32 |
| Silver | off / on | 1.61 / 1.41 | +11.02% / +7.83% | 0.85 / 0.63 |
| AUDUSD | off / on | 1.66 / 1.67 | +21.13% / +17.70% | 1.35 / 1.32 |
| USDJPY | off / on | 1.32 / 1.32 | +9.11% / +9.11% | 0.64 / 0.64 |

**Finding:** on price-only backtests the avoid-filter is neutral-to-slightly
negative for these *swing* strategies. Trades are held for days, so a single
event during the hold is rarely decisive, and the move sometimes helps.

**But we keep it, defaulting OFF for backtest / ON for live**, because a
backtest models a *fixed* spread. In reality spreads widen sharply and slippage
spikes during NFP/FOMC - a real cost the historical data can't show. The live
bot will also use the ForexFactory high-impact feed (CPI, PPI, rate decisions).

Later option: **surprise mode** - trade the direction of a data surprise
(actual vs forecast) rather than avoiding it. More complex; deferred.


---

## Fair Value Gap (FVG) strategy — tested, REJECTED

Mined the Fair Value Gap concept from the EA indicator repo (SMC pack, Indi 39/92)
and implemented an FVG pullback-continuation strategy (`src/strategy/fvg.py`):
enter on a retrace into a fresh 3-candle imbalance, aligned with the daily trend.

Walk-forward out-of-sample results:

| Instrument | PF | Return | Max DD | Sharpe | Verdict |
|---|---|---|---|---|---|
| BTC | 0.84 | −12.1% | 30.4% | −0.19 | loses (in-sample +27% was overfit) |
| Gold | 1.14 | +12.2% | 26.6% | 0.58 | profitable but worse than trend (Sharpe 1.35, 5.9% DD) |
| Silver | 1.24 | +11.9% | 14.2% | 0.72 | profitable but worse than trend (Sharpe 0.85) |
| AUDUSD | 0.60 | −25.7% | 36.9% | −0.94 | loses badly |
| USDJPY | 0.65 | −8.9% | 22.8% | −0.36 | loses |

**Decision: NOT added to the portfolio.** FVG is a real concept (positive OOS on
gold/silver) but is dominated by our existing trend strategies there and loses on
the other three instruments. Its big in-sample BTC result collapsed out-of-sample
— a clean example of walk-forward catching overfitting before any money is risked.
The code is kept as a validated experiment for reference.


---

## Order Block & Liquidity Sweep — tested (1 candidate found)

Mined two more concept families from the EA repo and walk-forward tested them:
`src/strategy/order_block.py` (SMC continuation) and
`src/strategy/liquidity_sweep.py` (ICT stop-hunt reversal).

Order Block continuation (OOS):

| Instrument | PF | Return | Max DD | Sharpe | Verdict |
|---|---|---|---|---|---|
| BTC | 0.71 | -15.5% | 29.1% | -0.63 | loses |
| Gold | 1.21 | +6.7% | 8.3% | 0.56 | worse than trend |
| **Silver** | **1.67** | **+19.2%** | **5.9%** | **1.30** | **beats incumbent trend** |
| AUDUSD | 0.36 | -19.0% | 26.8% | -1.18 | loses |
| USDJPY | 1.23 | +9.8% | 9.2% | 0.50 | worse than MR |

Liquidity Sweep reversal (OOS): positive but dominated on gold/silver/AUD/JPY
(+2.8%/+9.8%/+9.8%/+18.3%), loses on BTC. No slot won. **Rejected.**

**Candidate found: Order Block on SILVER.** It is a Pareto improvement over the
incumbent silver trend strategy (+19.2% vs +11%, Sharpe 1.30 vs 0.85, 5.9% vs
6.9% max DD) — same instrument, period and trend filter, just better entry
timing. Caveat: ~26 OOS trades is a modest sample, and we tested ~15
strategy×instrument combos, so multiple-comparisons luck can't be ruled out.
**Decision: do NOT blind-swap; A/B test Silver-OB vs the trend version on demo.**
All other OB/Sweep results rejected.


---

## Volatility targeting — KEPT (selectively)

Evidence-backed enhancement (Moreira & Muir; vol-scaled momentum literature):
scale the risk fraction inversely to how current volatility compares to its own
trailing norm (`src/risk/vol_target.py`). Walk-forward, WITH vs WITHOUT:

| Instrument | Strategy | Sharpe off→on | Return off→on | Max DD off→on |
|---|---|---|---|---|
| BTC | trend | 0.76 → 0.31 | +19.6% → +6.2% | 13.5% → 15.5% |
| Gold | trend | 1.35 → 0.88 | +13.9% → +8.9% | 5.9% → 8.3% |
| Silver | trend | 0.85 → 0.99 | +11.0% → +14.7% | 6.9% → 6.2% |
| AUDUSD | mean-rev | 1.27 → **1.54** | +18.9% → +25.0% | 9.1% → 8.8% |
| USDJPY | mean-rev | 1.18 → **1.54** | +17.9% → +24.7% | 11.9% → **8.4%** |

**Finding: it is NOT universally good.** It HURTS trend-following (de-risks
exactly during the volatile expansions that produce trend's skew-driven tail
winners) but clearly HELPS mean-reversion (protects it in turbulent regimes).

**Decision: apply it selectively — ON for the mean-reversion sleeve (AUDUSD,
USDJPY), OFF for the trend sleeve (gold, silver, BTC).** This is a principled,
mechanism-based rule (by strategy type), not per-instrument fitting. Wired into
both backtest (`vol_scalar`) and live (`PortfolioSlot.use_vol_target` →
`decide(risk_scalar=...)`). Net effect on the FX slots: OOS Sharpe ~1.2 → ~1.5
with lower drawdown.
