# Running the Bot 24/7 (Windows VPS)

Your laptop can't stay on all the time — so we run the bot on a **VPS** (Virtual
Private Server): a computer in the cloud that is always on. You set it up once,
and it keeps trading even when your laptop is off.

## Important: which kind of "VPS"?

MetaTrader 5 has a built-in **"Virtual Hosting"** feature — but that ONLY runs
MQL5 Expert Advisors, **not Python scripts**. Our bot is Python, so we need a
**full Windows VPS** where we install MT5 *and* Python.

> (If you ever want the ultra-cheap MT5 built-in VPS, we'd have to rewrite the
> strategy as an MQL5 EA — a bigger project. Not needed now.)

## 1. Get a Windows VPS

Any of these work (swing trading on H4 doesn't need low latency, so location and
speed barely matter — pick cheap and reliable):

- **Forex-focused Windows VPS** providers (marketed for MT4/MT5) — easiest,
  usually ~$5–20/month, MT5-ready.
- **General cloud**: AWS EC2 (Windows), Azure, Google Cloud, Contabo, Vultr,
  Hetzner — a small/basic Windows instance (1–2 vCPU, 2–4 GB RAM) is plenty.
- **Check JustMarkets** — some brokers offer a **free VPS** to clients who meet
  a deposit/volume condition. Ask their support.

Minimum spec: Windows Server 2019/2022 (or Windows 10/11), 2 GB RAM, 2 vCPU.

## 2. Connect to it (Remote Desktop)

The provider gives you an IP address, username, and password. On your laptop,
open **"Remote Desktop Connection"** (built into Windows), enter the IP, and log
in. You now see the VPS desktop in a window. Everything below is done ON the VPS.

## 3. Set up the VPS (one time)

Do exactly what you did on your laptop:

1. Install **MetaTrader 5**, log into your JustMarkets account, and enable
   `Tools -> Options -> Expert Advisors -> Allow algorithmic trading` + the green
   **Algo Trading** button.
2. Install **Python 3.12+** (tick "Add Python to PATH"). *(3.12 or 3.13 is a
   slightly smoother choice than 3.14 for library support.)*
3. Install **Git** (or download the repo as a ZIP).
4. In Command Prompt:
   ```bat
   git clone https://github.com/klingesh/Tradingbot.git
   cd Tradingbot
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   pip install MetaTrader5
   ```
5. Run `python scripts/check_mt5.py` and confirm/update the symbol map in
   `config/live_config.yaml` (VPS symbols should match, but verify).
6. Test with `python scripts/dry_run_once.py`, then a `--confirm` order test.

## 4. Keep it running (and auto-restart)

Use the included **`scripts\run_bot.bat`** — it launches the bot and automatically
restarts it if it ever crashes:

```bat
scripts\run_bot.bat
```

To make it **start automatically when the VPS boots/logs in**:
1. Press `Win + R`, type `shell:startup`, press Enter (opens the Startup folder).
2. Right-click `scripts\run_bot.bat` -> "Create shortcut", and move the shortcut
   into that Startup folder.

Now if the VPS reboots, the bot relaunches on its own.

> Tip: keep MT5 set to auto-login and auto-start too (it usually reopens the last
> session). The bot connects to whatever account MT5 is logged into.

## 5. Monitor it remotely

- RDP in any time to watch the console / MT5.
- Run `python scripts\report.py` to see live performance (win rate, P&L,
  per-symbol) pulled from the broker.
- The bot writes `logs\journal.csv` (actions + equity snapshots).

## Safety reminders

- Keep `dry_run: false` only after you're happy with demo behaviour.
- The kill switches (drawdown / daily loss / max open trades) run on the VPS too.
- Start on the **demo** account on the VPS as well; move to live only later with
  tiny risk and after re-running `check_mt5.py` for the live account's symbols.

## Cost check

A basic Windows VPS is ~$5–20/month. For a demo run you could even keep using
your laptop when convenient; the VPS matters most once you go live and want
uninterrupted uptime.
