# Monitoring the live bot

The bot runs unattended on a VPS. This describes what it now writes down, so its
health can be checked without attaching to MetaTrader.

## Why this exists

Two things were wrong with an unattended 24/7 bot.

**The kill switch could be reset by a crash.** `scripts/run_bot.bat` restarts the
bot thirty seconds after any exit, forever. The drawdown baseline used to be taken
from whatever the balance was at connect time, so a bot that had drawn down 15%,
hit an MT5 disconnect and restarted would measure its next drawdown from the
already-reduced balance — and could lose another 20% before the switch meant to
stop it fired. The halt itself did not survive either: `_halted` reset to `False`,
so a halted bot resumed trading half a minute later.

**Nothing durable recorded what happened.** Logging went to the console only, and
the restart wrapper does not redirect it, so the kill-switch message scrolled away
with the window. A crash-loop was invisible.

## What the bot writes

All three live in `logs/`, which is gitignored — broker data never reaches GitHub.

| File | Contents | Rewritten |
| --- | --- | --- |
| `logs/bot.log` | Full log, rotating: 5 files × 2 MB | continuously |
| `logs/state.json` | Safety state: baseline, halt, day | on change |
| `logs/status.json` | Health snapshot for watchers | every poll |
| `logs/journal.csv` | Equity, actions, **and now events** | every poll / decision |

### `logs/status.json`

```json
{
  "heartbeat": "2026-08-11T09:14:02+00:00",
  "equity": 10412.55,
  "balance": 10400.00,
  "peak_equity": 10633.10,
  "baseline_balance": 10633.10,
  "drawdown_percent": 2.08,
  "drawdown_limit_percent": 20.0,
  "day_drawdown_percent": 0.4,
  "day_loss_limit_percent": 6.0,
  "halted": false,
  "new_entries_blocked": false,
  "dry_run": false,
  "open_count": 2,
  "open_positions": [{"symbol": "XAUUSD", "side": "buy", "lots": 0.12, "profit": 12.4}],
  "restarts": 0,
  "recent_errors": []
}
```

**`heartbeat` is the field that matters.** With `poll_seconds: 60` the bot rewrites
this every minute. Nothing else can tell a watcher on another machine that the
process has stopped — a dead bot looks exactly like a bot that has found nothing to
trade, unless the timestamp is going stale. Treat anything older than about five
minutes as stopped.

`restarts` exposes crash-looping, which the restart wrapper otherwise hides
completely.

### `logs/journal.csv`

Now carries a third row kind alongside `equity` and `action`:

| `kind` | When |
| --- | --- |
| `event` | `start`, `kill_switch`, `daily_loss_halt` |

A halt now sits in the same timeline as the trades that caused it.

## The baseline is a high-water mark

`state.json` keeps `start_balance`, and the kill switch measures against it. It
**rises** when the balance rises — real profit or a deposit should move the
goalposts up — and **never falls on a restart**. That is what stops a crash from
forgiving a drawdown that already happened.

## Clearing a halt

A kill-switch halt is now permanent until a human clears it. That is deliberate:
the switch exists precisely for the case where the bot should not decide for itself
that it may resume.

On the VPS, stop the bot, then:

```
del logs\state.json
```

Restarting rebuilds the baseline from the current balance. **Understand what you
are doing before you do this** — you are telling the bot that its current, reduced
balance is the new normal.

If the bot starts while still halted it says so, loudly:

```
ERROR trader: STILL HALTED from a previous run (total drawdown 21.30% >= 20.00%
at 2026-08-10T22:41:07+00:00). No new entries will be taken.
Delete logs/state.json to clear.
```

## Checking on it by hand

```
type logs\status.json
```

```
python scripts\report.py
```

`report.py` reads realised P&L from the broker's own deal history, which remains
the source of truth for money. `status.json` is the bot's view of itself.

## Watching it from another machine

The bot runs on a VPS. Whatever watches it usually does not, and there is no way
to read `logs/status.json` across that gap — so `scripts/publish_status.py` pushes
it to a private GitHub repository that both ends can reach.

GitHub is the transport for three practical reasons: nothing has to be opened on
the VPS firewall, no new service has to be run or paid for, and the result is
readable from a phone. It is not a clever choice; it is the one with the fewest
moving parts.

### Setup

Create a **private** repository — `status.json` carries your equity, balance and
open positions, and publishing that publicly would put your account performance on
the internet.

Then generate a fine-grained token with **Contents: Read and write** on that
repository only, and:

```
copy config\publish.example.yaml config\publish.yaml
notepad config\publish.yaml
```

Fill in `repo` and `token`. Prefer setting `STATUS_TOKEN` in the environment
instead, so the token never lands on disk on a VPS that might be snapshotted.

Check it before letting it loose:

```
python scripts\publish_status.py --dry-run
```

That renders what would be published and sends nothing. Then:

```
python scripts\publish_status.py --once
```

### Running it

```
scripts\run_publisher.bat
```

Put a shortcut in the Startup folder beside `run_bot.bat`.

**It runs as its own process, never inside the trading loop.** A network call that
hangs would delay a tick, and monitoring must not be able to interfere with the
thing it monitors.

### How often it publishes

Every `interval_seconds` (default 300) when nothing notable is happening, and
**immediately** when any of these change:

- `halted` / `day_halted` / `new_entries_blocked`
- `open_count` — a position opened or closed
- `restarts` — the bot is crash-looping
- a new entry in `recent_errors`
- `dry_run` — the difference between logging trades and placing them

The heartbeat and equity are deliberately excluded from that list. Both move every
cycle, so treating them as notable would mean 1,440 commits a day saying nothing.

Two files appear in the status repo: `status.json` for a monitor to parse, and
`STATUS.md` for a person to open in the GitHub app.

## A note on scope

Everything here is **read-only reporting**. Nothing in this file starts, stops or
modifies a trade. The same discipline applies as to the news tools in
`docs/NEWS_TOOLS.md`: inform the human, and stay out of the order path.
