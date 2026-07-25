# Running the Bot on Windows (JustMarkets MT5 — Demo First)

This guide gets the bot running on your Windows laptop against your JustMarkets
**demo** account. Do every step on demo until you've seen it behave for a while.

> ⚠️ Never point this at a live account until it has run cleanly on demo and you
> understand exactly what it does. Trading involves real risk of loss.

---

## 0. Prerequisites

- Windows PC with **MetaTrader 5** installed and **logged into your JustMarkets
  DEMO account**.
- **Python 3.11+** installed (during install, tick "Add Python to PATH").
- Git (optional, or download the repo as a ZIP from GitHub).

## 1. Enable algorithmic trading in MT5

In MetaTrader 5:
1. `Tools -> Options -> Expert Advisors`.
2. Tick **"Allow algorithmic trading"**.
3. Click the **"Algo Trading"** button in the top toolbar so it's green.
4. Add your instruments to **Market Watch** (right-click Market Watch ->
   "Symbols", enable Gold, Silver, AUDUSD, USDJPY). The bot can select them too,
   but this makes discovery reliable.

## 2. Get the code and install dependencies

Open **Command Prompt** (or PowerShell):

```bat
git clone https://github.com/klingesh/Tradingbot.git
cd Tradingbot

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
pip install MetaTrader5
```

## 2b. Create your live config (first run only)

Your personal config is gitignored so it never conflicts with `git pull`. Copy
the template once:

```bat
copy config\live_config.example.yaml config\live_config.yaml
```

(Mac/Linux: `cp config/live_config.example.yaml config/live_config.yaml`.)
Then edit `config/live_config.yaml` in the next steps.

## 3. Discover your symbol names + specs (STEP 1 script)

Cent accounts often rename symbols (e.g. `XAUUSD.c`). Find the real names:

```bat
python scripts/check_mt5.py
```

This prints your account info and, for each instrument, the matching symbol(s)
and their contract specs. Copy the **"SUGGESTED SYMBOL MAP"** into
`config/live_config.yaml` under `symbols:`.

If something shows "NO MATCH", add that instrument to Market Watch and re-run.

## 4. Review the config

Open `config/live_config.yaml` and check:
- `dry_run: true`  ← keep this for now.
- `symbols:` match what step 3 printed.
- `risk.risk_percent_per_trade` (default 2.0) and the safety caps.
- `news_filter.enabled: true`.

## 5. Dry run (no orders sent)

```bat
python live_trader.py
```

The bot connects and, on each **closed H4 bar**, logs what it *would* do
(ENTER/SKIP/HOLD/CLOSE) with lot sizes and SL/TP — but sends **no orders**.

- H4 bars close every 4 hours, so leave it running to see activity.
- Watch that: it connects, reads your balance, finds symbols, sizes positions
  sensibly, and respects the news blackout. Look for lines like
  `[GOLD/XAUUSD] ENTER BUY 0.12 lots  SL=... TP=... [DRY RUN] order not sent.`

## 6. Demo orders (still the demo account!)

When the dry-run logs look right, set `dry_run: false` in the config and run
again. Now it places **real orders on your DEMO account**, with SL/TP attached.

- Let it run for days/weeks. Compare its behaviour to the backtest expectations.
- Keep the laptop awake (disable sleep) or move to a Windows VPS for 24/7.

## 7. Safety features (already built in)

- **Kill switch**: halts entirely if total drawdown hits
  `max_total_drawdown_percent` (default 20%).
- **Daily-loss limit**: stops new entries for the day past
  `max_daily_loss_percent` (default 6%).
- **max_open_trades**: caps concurrent positions.
- **Magic number**: the bot only touches its own trades.
- **News blackout**: skips entries around high-impact events.

Stop the bot any time with **Ctrl+C**.

## Troubleshooting

- **"MetaTrader5 initialize failed"** — MT5 must be running and logged in; enable
  "Allow algorithmic trading" (step 1). Try running Command Prompt as admin.
- **"Could not select symbol"** — wrong name; re-run `check_mt5.py` and update
  the map. Add the symbol to Market Watch.
- **Order fails with "unsupported filling mode"** — the connector auto-detects
  the mode; if a specific symbol still fails, tell me the symbol and error code.
- **Timezone note** — MT5 candle times are in the broker's server time. We label
  them UTC. For H4 swing this is fine; if the daily trend filter looks shifted,
  tell me your broker's server offset and I'll adjust.

## What's next

Once demo trading looks healthy, we can add: performance logging/dashboards,
periodic parameter re-optimization, and a Windows VPS deployment for 24/7 uptime.
