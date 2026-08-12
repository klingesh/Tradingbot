# Hardening log: making an unattended bot safe to leave alone

`docs/DEVELOPMENT_JOURNEY.md` covers how the strategy was built and validated.
This covers what happened **after** it was deployed to a VPS and left running —
the faults that only appear once nobody is watching, and what each one cost to
find.

Every entry follows the same shape: the symptom as it actually appeared, the
cause, and the fix. Nothing here is hypothetical; each item was observed on the
live install, most of them on real broker data.

> Read `docs/MONITORING.md` for how the resulting system works. This file is the
> record of *why* it is shaped that way.

---

## The theme

The strategy was validated carefully. The **operational** layer was not, and that
is where every fault in this log lives.

`scripts/run_bot.bat` restarts the bot thirty seconds after any exit, forever.
That single line of convenience is the root of the first three entries: an
auto-restart wrapper turns a crash from an event into a *state transition*, and
any safety mechanism that lives only in memory is quietly reset by it.

The pattern that kept repeating: **a wrong number is more dangerous than a missing
one.** A blank field is obviously broken. A plausible, confident, wrong field
sends you to debug the wrong thing — or worse, reassures you.

---

## 1. The kill switch could be reset by a crash

**Symptom.** None visible. That is what made it serious.

**Cause.** The drawdown baseline was taken from whatever the balance happened to be
at connect time, and `_halted` was an in-memory flag.

So a bot that had drawn down 15%, hit an MT5 disconnect and restarted would
measure its next drawdown from the *already reduced* balance — and could lose
another 20% before the switch meant to stop it fired. The halt did not survive
either: `_halted` reset to `False`, and a halted bot resumed trading half a minute
later.

Over two weeks of unattended running, that is not a hypothetical.

**Fix.** Safety state moved to `logs/state.json` — the drawdown baseline, the halt
and its reason, and the day's opening equity.

The baseline is a **high-water mark**: it rises when the balance rises, because
real profit or a deposit should move the goalposts up, and it *never* falls on a
restart. That last property is the entire point.

A kill-switch halt is now permanent until a human deletes the file, and the bot
announces it loudly on startup:

```
ERROR trader: STILL HALTED from a previous run (total drawdown 21.30% >= 20.00%
at 2026-08-10T22:41:07+00:00). No new entries will be taken.
Delete logs/state.json to clear.
```

Commit `1929d5c`. `src/live/state.py`, `src/live/trader.py`.

## 2. Nothing durable recorded what happened

**Symptom.** A crash-loop was invisible. So was every MT5 `initialize` failure and
every traceback.

**Cause.** `_setup_logging()` had no file handler, and the restart wrapper does not
redirect output — so the kill-switch message scrolled away with the console window.

**Fix.** Logging also goes to `logs/bot.log`, rotating at 5 files × 2 MB so an
unattended VPS cannot fill its disk. A read-only disk warns and carries on with
console logging rather than refusing to start — monitoring must never be the reason
the bot won't run.

Halts are journalled as a new `event` row kind in `logs/journal.csv`, so a halt sits
in the same timeline as the trades that caused it. They are logged **once per event**
rather than once per poll: at sixty-second intervals the old code wrote the same line
fourteen hundred times a day.

Commit `1929d5c`. `src/live/journal.py`.

## 3. A dead bot looked exactly like an idle one

**Symptom.** From another machine, a stopped process and a bot that has found
nothing to trade are indistinguishable.

**Fix.** `logs/status.json`, rewritten every cycle with equity, drawdown against
both limits, open positions, restart count and recent errors.

**`heartbeat` is the field that matters.** It is the only reliable way to tell that
the process has stopped — treat anything older than about five minutes as stopped.

Status writing is wrapped in a try/except so that **monitoring can never stop the
thing it monitors.**

Commit `1929d5c`.

## 4. The status file could not be read from anywhere useful

**Symptom.** The bot runs on a VPS. The thing that watches it does not.

**Fix.** `scripts/publish_status.py` pushes `status.json` to a **private** GitHub
repository that both ends can reach.

GitHub is the transport for three practical reasons: nothing has to be opened on the
VPS firewall, no new service has to be run or paid for, and the result is readable
from a phone. It is not a clever choice — it is the one with the fewest moving parts.

| Rejected | Why |
| --- | --- |
| HTTP endpoint on the VPS | An open port and authentication to get wrong |
| SSH | Poor fit for a Windows box reached by RDP |

Publishing is time-based with an override: every `interval_seconds` (default 300)
normally, and **immediately** when something worth knowing changes — a halt, a new
error, a position opening or closing, a restart, or `dry_run` flipping.

The heartbeat and equity are deliberately **excluded** from that test. Both move
every cycle, so including them would mean 1,440 commits a day to say nothing at all.

Two files are written: `status.json` for a monitor to parse, and `STATUS.md` for a
person to read in the GitHub app. The markdown leads with the *state* rather than the
numbers, and quotes drawdown against its limit — a number without its limit does not
tell you whether to worry.

The publisher is a **separate process** and is never called from the trading loop. A
network call that hangs would delay a tick.

Commit `26dfe63`. `scripts/publish_status.py`.

## 5. `--once` said nothing on success, and retried forever on failure

Three faults, all found by *running* it rather than reading it.

**Silent success.** The publish happened, the files appeared in the repo, and the
console printed only the startup banner. There was no way to tell it had worked
without going to GitHub to look. It now reports equity, drawdown against its limit,
open count and halted state:

```
INFO publisher: Published to klingesh/tradingbot-status: equity 9743.66,
drawdown 2.56% of 20.00%, 1 open, running.
```

**Infinite retry under `--once`.** The retry path called `continue`, which skipped
the `if args.once` check entirely — so a one-shot publish against a bad repo or an
expired token would back off and loop until killed. It now returns `1`. A missing
`status.json` under `--once` also returns `1` rather than `0`: exiting zero would
tell a caller it had published when it had not.

**Ctrl+C printed a traceback.** That is how this process is stopped, so it is not an
error — and dumping a stack over the operator's console while they are watching a
live trading bot is worse than merely untidy.

While fixing the third: `read_status()` took its path as a **default argument bound
at import time**, so the location could not be configured and the function could not
be tested. It is now a config key, `status_path`.

Commit `1947c1b`.

## 6. Every open position was reported as a buy

**Symptom.** Caught on live data. The bot opened a **short** Brent position and
published it as:

```json
{"symbol": "BRENT.ecn", "side": "buy", "open_price": 88.5,
 "sl": 92.08, "tp": 84.9}
```

A stop *above* the entry and a target *below* it is unambiguously a short. The label
was wrong, not the levels.

**Cause.** The mapping read `getattr(p, "type", 0) == 0`, but `OpenPosition` has no
`type` attribute — it has `side`, `+1` for long and `-1` for short. The `getattr`
default fired on every position, so the expression was **always true**.

**Why this is the worst shape a monitoring bug can take.** A missing figure is
obvious. A plausible wrong one is not — and "you are long Brent" when the account is
short is actively misleading.

**Fix.** The mapping was inline in `trader.py` behind the MT5 and pandas imports,
which is why it was never tested. It moved to `state.py` as `position_to_dict()`:
a short reports as a sell, a long as a buy, and an unrecognised or absent side
reports `"unknown"` rather than being guessed at. **Reporting the wrong direction
confidently is worse than reporting none.**

Commit `2ebe865`.

## 7. The publisher only ran when someone remembered to start it

**Symptom.** A **sixteen-minute-old** snapshot was being reported as live.

**Cause.** `run_publisher.bat` needs a console window, dies when it closes, and dies
when the RDP session logs off.

A Startup-folder shortcut is not enough either: it only runs when a user logs in
*interactively*. If the VPS reboots and nobody opens an RDP session, nothing starts —
precisely the situation where remote monitoring matters most.

**Fix.** `scripts/install_publisher_task.bat` registers a scheduled task
(`BeasttStatusPublisher`) that runs at startup **as SYSTEM**, so it needs no login and
survives logging off, and starts it immediately so no reboot is required.

`scripts/publisher_service.bat` is the unattended shape of the same loop, and three
details matter:

- it calls the venv's `python.exe` **directly** rather than activating the venv,
  because activation relies on a user environment SYSTEM does not have
- it derives an **absolute** working directory from its own location, because SYSTEM
  starts in `system32`
- it writes to a **log**, because there is no console

**The trading bot itself stays in the Startup folder.** MetaTrader needs an
interactive desktop session; the publisher only reads a file and makes an HTTPS
request, so it is happy as SYSTEM.

The `schtasks` invocation is deliberately on a single line — line continuations plus
nested quotes are a reliable way to register a task whose action is subtly wrong.

**Do not run both** the task and `run_publisher.bat`. Two publishers each fetch the
file's blob sha and then both try to replace it, so one is rejected on every push.

Commit `c61b58a`.

## 8. Two bots ran on the same account at once

**Symptom.** An impossible number. The published restart counter went **3, 4, 3, 4** —
and a counter cannot decrease.

**Cause.** Two `live_trader.py` processes. Each had loaded `state.json` at its own
start time, so each held its own copy of the safety state in memory and overwrote the
other's `status.json` on alternating ticks — thirty seconds apart on a sixty-second
poll.

On a machine reached by RDP this is easy to do by accident: start the bot, lose the
session, reconnect, start it again. Nothing objected.

**Why the confused reporting is the least of it.** Both instances evaluate the same
signals against the same account under the same magic number, and each carries its own
drawdown baseline — so the kill switch is **split in two** and neither half sees the
whole loss. A safety limit that two processes disagree about is not a limit.

**Fix.** `run()` takes an exclusive lock before loading the config, and exits naming
the lock file if it cannot:

```
ERROR trader: Not starting: another bot process is already running. Stop it before
starting another, or delete logs/bot.lock only if you are certain nothing is running.
```

The lock comes from the **operating system** rather than a pid file. A pid file has to
answer "is that process still alive", which is awkward on Windows and wrong once the
number has been reused; a kernel lock is dropped when the holder dies, however it
dies. So a crash cannot leave a stale lock — a leftover lock *file* is harmless, and
that case is tested.

The existing file is opened `r+` rather than `w`, so a refused second start does not
truncate the running instance's recorded pid before discovering it is not allowed to
have it.

`run_once()` is deliberately left **unlocked**: `dry_run_once.py` places no orders and
is the tool you reach for while the bot is running.

Commit `0e5086a`. `src/live/lock.py`.

## 9. The lock was dropped the instant it was taken

**Symptom.** A second bot started with no complaint — on Windows, with every test
passing.

**Cause.** Not Windows. Not file locking. Object lifetime.

```python
SingleInstance().acquire()
```

The result was discarded. Nothing referenced the object once that statement ended, so
CPython freed it immediately — closing the file handle and letting the kernel release
the lock. The next process found the file unlocked and ran.

**Every test passed** because every test assigned the result to a local, which kept it
alive for the duration. The one call site that mattered did not, and no test covered
it. Reproduced on POSIX in three lines, so this was never platform-specific.

**Fix.** `hold()` owns a module-level reference and is what `run()` calls. It is
idempotent, so a second call inside the same process returns the same lock rather than
deadlocking against itself.

Three of the five new tests are about the *shape* of the mistake rather than the
behaviour: one documents the discarded-reference failure directly, one proves `hold()`
survives a forced garbage collection, and one **reads `trader.py` and fails if the
bare-acquire pattern reappears at the call site** — because the call site is what
broke, not the lock.

That last guard immediately caught an explanatory comment quoting the forbidden
pattern, which is a fair indication it is looking in the right place.

Commit `f4cac09`.

## 10. Crash-looping is a rate, not a lifetime total

**Symptom.** A monitor announced "possibly crash-looping" about a bot that had been
stable for hours.

**Cause.** It was right about the number and wrong about the meaning. The bot had been
restarted nine times **by hand** that morning during an unrelated cleanup, and
`restarts` is a lifetime counter that never resets.

Any threshold on a number which only rises **fires forever once crossed** — which is
exactly how a warning turns into noise to be dismissed, and then the real one is
dismissed with it.

**Fix.** State now records **when** each restart happened, pruned to the last day and
capped at 200 entries — bounded by *age* so it reflects recent behaviour, and by
*length* so a bot restarting every thirty seconds cannot grow the state file without
limit.

`status.json` gains `restarts_last_hour` and `restarts_last_day` alongside the lifetime
figure. Those are the numbers a watcher should judge on.

The lifetime count stays. It is useful history; it is just not evidence of anything
happening *now*.

Commit `99bfc4f`.

---

## Operator gotchas

Things that cost real time on the VPS and are not bugs.

**A new script isn't there until you pull.**

```
C:\Tradingbot>scripts\install_publisher_task.bat
'scripts\install_publisher_task.bat' is not recognized as an internal or external command,
operable program or batch file.
```

`cmd` reports a *missing file* with the same wording it uses for a bad command, which
reads like a syntax problem. Run `git pull`, then `dir scripts\install_publisher_task.bat`
to confirm before blaming the script.

**The task installer needs Administrator.** It refuses politely rather than failing
halfway, and prints the action it registered so a mis-quoted path is visible now
instead of days later as "why has nothing published".

**Never run two publishers.** See entry 7.

**Clearing a halt is a decision, not a step.** `del logs\state.json` tells the bot that
its current, reduced balance is the new normal. Understand why the switch fired first.

---

## What the tests cover

65 checks across the safety and monitoring layer:

| File | Checks | Covers |
| --- | --- | --- |
| `tests/test_state.py` | 28 | Baseline high-water mark, halt persistence, position mapping, restart rates |
| `tests/test_publish_status.py` | 22 | Contents API create vs update, backoff, `--once` exit codes |
| `tests/test_lock.py` | 15 | Exclusive locking, stale lock files, the discarded-reference regression |

Several are **reported failures written out as fixtures** — the nine-restarts false
alarm, the mislabelled Brent short. A bug that shipped once should not be able to
ship twice.

---

## The lessons

1. **An auto-restart wrapper turns crashes into state transitions.** Any safety
   mechanism that lives only in memory is silently reset by it.
2. **A confidently wrong number beats a missing one, and not in a good way.**
3. **Alert on rates and changes, never on lifetime totals.** A threshold on a
   monotonically rising number fires forever.
4. **Monitoring must not be able to break what it monitors** — separate process,
   wrapped writes, no network calls in the trading loop.
5. **Test the call site, not just the function.** Entry 9 passed every unit test.
6. **Run it, don't read it.** Entries 5, 6, 7, 8 and 10 were all found by operating
   the thing, not by review.
7. **Unattended means "no console, no login, no user profile."** Assumptions about the
   environment are the whole difficulty in entry 7.

## Scope

Everything in this log is **read-only reporting**. Nothing described here starts, stops
or modifies a trade. The same discipline applies as to the news tools in
`docs/NEWS_TOOLS.md`: inform the human, and stay out of the order path.
