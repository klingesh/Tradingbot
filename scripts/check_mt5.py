"""
STEP 1 (run this first on your Windows laptop).

Verifies the MT5 connection and DISCOVERS the exact symbol names + contract
specs on your JustMarkets account. Cent accounts often append suffixes
(e.g. "XAUUSD.c", "AUDUSD_c"), so we can't assume names - we look them up.

Usage (Windows, MT5 running and logged into your DEMO account):
    python scripts/check_mt5.py

Copy the "SUGGESTED SYMBOL MAP" it prints into config/live_config.yaml.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.connectors import MT5Connector

# What we want to trade -> search hints to find the broker's real name.
WANTED = {
    "GOLD":     ["XAUUSD", "XAU", "GOLD"],
    "SILVER":   ["XAGUSD", "XAG", "SILVER"],
    "NATGAS":   ["NGAS", "NATGAS", "XNG", "GAS"],
    "PLATINUM": ["XPTUSD", "XPT", "PLAT"],
    "GBPJPY":   ["GBPJPY"],
    "AUDUSD":   ["AUDUSD"],
    "USDJPY":   ["USDJPY"],
    "BRENT":    ["UKOIL", "BRENT", "XBR", "UKOUSD"],
    "BTC":      ["BTCUSD", "BTC"],
}


def main() -> None:
    c = MT5Connector()
    if not c.available():
        print("MetaTrader5 package not installed. On Windows run: pip install MetaTrader5")
        return

    print("Connecting to MT5 (using the account currently logged into the terminal)...")
    acct = c.connect()  # uses the terminal's logged-in account
    print("\n=== ACCOUNT ===")
    print(f"  Login:    {acct.login}")
    print(f"  Balance:  {acct.balance:,.2f} {acct.currency}")
    print(f"  Equity:   {acct.equity:,.2f} {acct.currency}")
    print(f"  Leverage: 1:{acct.leverage}")
    print(f"  Free margin: {acct.margin_free:,.2f} {acct.currency}")
    if acct.currency in ("USC", "USX") or acct.currency.endswith("C"):
        print("  -> Looks like a CENT account (balance shown in cents).")

    print("\n=== SYMBOL DISCOVERY + SPECS ===")
    suggested: dict[str, str] = {}
    for logical, hints in WANTED.items():
        candidates: list[str] = []
        for h in hints:
            for s in c.list_symbols(h):
                if s not in candidates:
                    candidates.append(s)
        if not candidates:
            print(f"\n{logical}: NO MATCH found. Check your Market Watch / broker names.")
            continue

        # Prefer the shortest exact-ish match (usually the primary symbol).
        best = sorted(candidates, key=len)[0]
        suggested[logical] = best
        print(f"\n{logical}: candidates = {candidates}")
        try:
            d = c.symbol_details(best)
            print(f"  chosen: {best}  ({d['description']})")
            print(f"    digits={d['digits']}  point={d['point']}  "
                  f"tick_size={d['trade_tick_size']}  tick_value={d['trade_tick_value']}")
            print(f"    contract_size={d['trade_contract_size']}  "
                  f"vol_min={d['volume_min']}  vol_step={d['volume_step']}  vol_max={d['volume_max']}")
            print(f"    spread={d['spread']} points  min_stop_dist={d['trade_stops_level']} points")
        except Exception as e:
            print(f"  Could not read specs for {best}: {e}")

    print("\n=== SUGGESTED SYMBOL MAP (paste into config/live_config.yaml) ===")
    print("symbols:")
    for logical, real in suggested.items():
        print(f"  {logical}: {real}")

    c.shutdown()
    print("\nDone. If names look wrong, run again after adding the instruments to Market Watch.")


if __name__ == "__main__":
    main()
