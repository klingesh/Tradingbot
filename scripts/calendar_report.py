"""
Economic-calendar awareness report (informational).

Shows this week's high-impact events and, for each instrument in your portfolio,
which events will put it in a NEWS BLACKOUT (when the bot won't open new trades)
and when. Turns "what's happening this week?" into a glance.

Usage (works anywhere - no MT5 needed):
    python scripts/calendar_report.py
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from src.news.calendar import ForexFactoryCalendar
from src.live.portfolio import DEFAULT_PORTFOLIO, OPTIONAL_CRYPTO

BLACKOUT_BEFORE_MIN = 120
BLACKOUT_AFTER_MIN = 120


def main() -> None:
    now = pd.Timestamp.now(tz="UTC")
    try:
        events = ForexFactoryCalendar().events(week="thisweek", min_impact="High")
    except Exception as e:
        print(f"Could not fetch calendar: {e}")
        return

    upcoming_all = [e for e in events if e.time_utc >= now]
    if not upcoming_all:
        print("\n  (Note: the free feed only serves the CURRENT calendar week. It's "
              "the weekend,\n   so all events shown are finished - re-run on/after "
              "Monday for the week ahead.)")

    print(f"\n=== HIGH-IMPACT EVENTS THIS WEEK (UTC)  [now: {now:%a %d %b %H:%M}] ===")
    by_day = defaultdict(list)
    for e in events:
        by_day[e.time_utc.strftime("%a %d %b")].append(e)
    for day, evs in by_day.items():
        print(f"\n  {day}")
        for e in evs:
            when = e.time_utc.strftime("%H:%M")
            flag = " <== upcoming" if e.time_utc >= now else ""
            print(f"    {when}  {e.currency:4} {e.title}{flag}")

    print("\n=== PER-INSTRUMENT BLACKOUT SCHEDULE ===")
    print("(the bot will NOT open new trades within "
          f"+/-{BLACKOUT_BEFORE_MIN}min of these events)\n")
    slots = list(DEFAULT_PORTFOLIO) + list(OPTIONAL_CRYPTO)
    before = pd.Timedelta(minutes=BLACKOUT_BEFORE_MIN)
    after = pd.Timedelta(minutes=BLACKOUT_AFTER_MIN)

    for slot in slots:
        relevant = [e for e in events if e.currency in slot.news_currencies]
        upcoming = [e for e in relevant if e.time_utc + after >= now]
        currently = [e for e in relevant if (e.time_utc - before) <= now <= (e.time_utc + after)]
        status = "IN BLACKOUT NOW" if currently else "clear"
        ccy = "/".join(sorted(slot.news_currencies))
        print(f"  {slot.logical:9} [{ccy:9}] {status}")
        for e in upcoming[:4]:
            delta = e.time_utc - now
            hrs = delta.total_seconds() / 3600
            tag = f"in {hrs:.1f}h" if hrs >= 0 else f"{-hrs:.1f}h ago"
            print(f"        {e.time_utc:%a %H:%M} UTC  {e.title[:48]:48} ({tag})")
        if not upcoming:
            print("        (no upcoming high-impact events this week)")

    print("\nNote: informational. The bot already enforces these blackouts "
          "automatically when live.")


if __name__ == "__main__":
    main()
