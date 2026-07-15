"""
Entry point for live/demo trading (run on Windows with MT5 running).

    python live_trader.py

Reads config/live_config.yaml. Start with dry_run: true and watch the logs
before ever sending real orders. Always validate on a DEMO account first.
"""

from src.live.trader import run

if __name__ == "__main__":
    run("config/live_config.yaml")
