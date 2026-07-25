"""
News-sentiment dashboard (INFORMATIONAL - for your eyes, not the bot's).

Fetches recent forex + geopolitical/macro headlines, scores their financial
tone, and shows a per-instrument + macro "radar". This informs YOUR discretionary
decisions; it does NOT drive automated trades (by design - see docs).

Usage (works anywhere - no MT5 needed):
    python scripts/news_dashboard.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from src.news.sentiment import (
    fetch_headlines, aggregate, tone_label, INSTRUMENT_QUERIES, MACRO_TOPICS,
)
from src.live.portfolio import DEFAULT_PORTFOLIO, OPTIONAL_CRYPTO


def bar(tone: float, width: int = 21) -> str:
    """A little -1..+1 gauge."""
    mid = width // 2
    pos = int(round((tone + 1) / 2 * (width - 1)))
    cells = ["-"] * width
    cells[mid] = "|"
    cells[max(0, min(width - 1, pos))] = "#"
    return "".join(cells)


def show(title: str, query: str) -> None:
    try:
        hs = fetch_headlines(query, within_days=4, limit=15)
    except Exception as e:
        print(f"  {title:20} (fetch failed: {str(e)[:40]})")
        return
    agg = aggregate(hs)
    if agg["n"] == 0:
        print(f"  {title:20} no recent headlines")
        return
    print(f"  {title:20} [{bar(agg['tone'])}] {agg['tone']:+.2f} {tone_label(agg['tone'])}"
          f"  ({agg['pos']}+/{agg['neg']}-/{agg['neutral']}o of {agg['n']})")
    for h in sorted(hs, key=lambda x: x.score)[:1] + sorted(hs, key=lambda x: -x.score)[:1]:
        mark = "+" if h.score > 0.05 else ("-" if h.score < -0.05 else "o")
        print(f"        [{mark}] {h.title[:78]}")
    time.sleep(0.3)


def main() -> None:
    now = pd.Timestamp.now(tz="UTC")
    print("=" * 78)
    print("  NEWS-SENTIMENT DASHBOARD  (INFORMATIONAL ONLY - not used for auto-trading)")
    print(f"  {now:%A %d %b %Y  %H:%M} UTC")
    print("=" * 78)
    print("  Tone is a crude headline heuristic and is NOT a price-direction signal.")
    print("  Use it as awareness for YOUR decisions, alongside the calendar report.\n")

    print("--- MACRO / GEOPOLITICAL ---")
    for title, query in MACRO_TOPICS.items():
        show(title, query)

    print("\n--- PORTFOLIO INSTRUMENTS ---")
    slots = list(DEFAULT_PORTFOLIO) + list(OPTIONAL_CRYPTO)
    seen = set()
    for slot in slots:
        if slot.logical in seen:
            continue
        seen.add(slot.logical)
        q = INSTRUMENT_QUERIES.get(slot.logical)
        if q:
            show(slot.logical, q)

    print("\nReminder: headline tone != future price move. This dashboard informs")
    print("you; the bot trades only its validated, backtested systematic edges.")


if __name__ == "__main__":
    main()
