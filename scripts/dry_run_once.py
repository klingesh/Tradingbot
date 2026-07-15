"""
STEP 2: one-shot dry run.

Connects, evaluates all portfolio instruments ONCE against their latest CLOSED
bar, logs exactly what the bot WOULD do (ENTER/SKIP/HOLD/NOTHING with lot sizes
and SL/TP), then exits. Sends NO orders while config dry_run is true.

Usage (Windows, MT5 open + logged into demo):
    python scripts/dry_run_once.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.live.trader import run_once

if __name__ == "__main__":
    run_once("config/live_config.yaml")
