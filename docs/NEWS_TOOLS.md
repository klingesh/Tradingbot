# News Awareness Tools (informational)

Two scripts give you a market-news "radar". Both are **informational only** — they
inform *your* decisions and do **not** drive the bot's automated trades. (News-
sentiment auto-trading is unbacktestable and latency-disadvantaged; the bot
sticks to its validated, backtested systematic edges. News is used by the bot
only as a *risk blackout*, never as a trade trigger.)

They run anywhere (no MT5 needed):

## 1. Economic-calendar report

```bash
python scripts/calendar_report.py
```

Shows this week's high-impact events (from the ForexFactory feed) and, per
portfolio instrument, which events will put it in a news blackout and when.
Run it on/after Monday for the week ahead (the free feed only serves the current
calendar week, so on weekends it shows the finished week).

## 2. News-sentiment dashboard

```bash
python scripts/news_dashboard.py
```

Fetches recent forex + macro/geopolitical headlines (Google News RSS), scores
each with a finance-tuned tone lexicon, and shows a per-instrument + macro radar
(e.g. Strait of Hormuz, Fed, oil). Each line shows a -1..+1 tone gauge and sample
headlines.

**Important:** headline *tone* is a crude heuristic and is **not** a price-
direction signal (markets are forward-looking; "good news" can sell off). Use it
as situational awareness, not a trade signal. The lexicon can later be swapped
for an LLM scorer via `src/news/sentiment.py` if you want richer analysis.
