"""
STEP 3 (optional but recommended): validate the ORDER pathway on DEMO.

This is the one thing we can't test off-Windows: does order_send actually work
with your broker's filling mode, and do SL/TP attach correctly? This script
places a MINIMUM (0.01 lot) market order with a wide SL/TP, prints the result,
then immediately closes it - so it leaves you flat.

    # preview only (sends nothing):
    python scripts/test_order.py

    # actually send a 0.01-lot test order on DEMO, then close it:
    python scripts/test_order.py --confirm

    # choose a different instrument:
    python scripts/test_order.py --symbol AUDUSD.ecn --confirm

>>> ONLY run --confirm on a DEMO account. <<<
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import yaml

from src.connectors import MT5Connector


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None, help="broker symbol (default: GOLD from config)")
    ap.add_argument("--side", default="buy", choices=["buy", "sell"])
    ap.add_argument("--confirm", action="store_true", help="actually send the order (else preview)")
    args = ap.parse_args()

    with open("config/live_config.yaml") as f:
        cfg = yaml.safe_load(f)
    symbol = args.symbol or cfg["symbols"]["GOLD"]
    magic = cfg["run"]["magic_number"]

    c = MT5Connector(magic=magic)
    if not c.available():
        print("MetaTrader5 not available (run on Windows).")
        return

    acct = c.connect()
    print(f"Connected. Login {acct.login}  Balance {acct.balance:,.2f} {acct.currency}")
    print(f"Test instrument: {symbol}")

    bid, ask = c.current_tick(symbol)
    side = 1 if args.side == "buy" else -1
    entry = ask if side == 1 else bid
    # Wide SL/TP (~2% away) so it won't trigger during the quick test.
    if side == 1:
        sl, tp = entry * 0.98, entry * 1.02
    else:
        sl, tp = entry * 1.02, entry * 0.98

    print(f"Would place: {args.side.upper()} 0.01 lots @ ~{entry}  SL={sl:.5f} TP={tp:.5f}")

    if not args.confirm:
        print("\nPreview only. Re-run with --confirm to actually send on DEMO.")
        c.shutdown()
        return

    print("\nSending test order...")
    res = c.place_market_order(symbol, side, 0.01, sl, tp, comment="test_order")
    print("  order result:", res)

    if res.get("ok"):
        print("ORDER OK. Waiting 3s, then closing it...")
        time.sleep(3)
        for p in c.bot_positions(symbol):
            close_res = c.close_position(p)
            print("  close result:", close_res)
        print("Done - you should be flat again.")
    else:
        print("ORDER FAILED. Paste the result above to Kiro so we can fix the "
              "filling mode / parameters for your broker.")

    c.shutdown()


if __name__ == "__main__":
    main()
