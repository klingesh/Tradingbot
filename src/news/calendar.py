"""
Economic calendar - high-impact events for the fundamentals layer.

Two sources:
  * DeterministicUSCalendar  - generates the biggest scheduled USD movers
    (Non-Farm Payrolls = always the first Friday; FOMC = published dates).
    Used for BACKTESTING because it needs no historical archive and the timing
    is exact.
  * ForexFactoryCalendar     - fetches the live high-impact feed (CPI, PPI, rate
    decisions, NFP, ...) for the RUNNING bot. Only covers last/this/next week,
    so it is for live use, not multi-year backtests.

All event times are stored in UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# FOMC interest-rate decision days (announcement ~14:00 ET). Published schedules.
FOMC_DECISION_DATES = [
    # 2023
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
    "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]


@dataclass(frozen=True)
class EconomicEvent:
    time_utc: pd.Timestamp
    currency: str
    title: str
    impact: str  # "High" | "Medium" | "Low"


def _et_to_utc(d: datetime, hh: int, mm: int) -> pd.Timestamp:
    """Build an aware UTC timestamp from an ET wall-clock time (handles DST)."""
    local = datetime.combine(d.date(), time(hh, mm), tzinfo=ET)
    return pd.Timestamp(local.astimezone(UTC))


def _first_friday(year: int, month: int) -> datetime:
    d = datetime(year, month, 1)
    # weekday(): Mon=0 ... Fri=4
    offset = (4 - d.weekday()) % 7
    return d + timedelta(days=offset)


class DeterministicUSCalendar:
    """High-confidence, exactly-timed US high-impact events for backtesting."""

    def __init__(self, include_nfp: bool = True, include_fomc: bool = True):
        self.include_nfp = include_nfp
        self.include_fomc = include_fomc

    def events(self, start: pd.Timestamp, end: pd.Timestamp) -> list[EconomicEvent]:
        start = pd.Timestamp(start).tz_convert(UTC) if start.tzinfo else pd.Timestamp(start, tz=UTC)
        end = pd.Timestamp(end).tz_convert(UTC) if end.tzinfo else pd.Timestamp(end, tz=UTC)
        out: list[EconomicEvent] = []

        if self.include_nfp:
            # NFP: first Friday of each month, 08:30 ET.
            y, m = start.year, start.month
            while datetime(y, m, 1, tzinfo=UTC) <= end.to_pydatetime():
                ff = _first_friday(y, m)
                ts = _et_to_utc(ff, 8, 30)
                if start <= ts <= end:
                    out.append(EconomicEvent(ts, "USD", "Non-Farm Payrolls", "High"))
                m += 1
                if m > 12:
                    m = 1
                    y += 1

        if self.include_fomc:
            for ds in FOMC_DECISION_DATES:
                d = datetime.strptime(ds, "%Y-%m-%d")
                ts = _et_to_utc(d, 14, 0)  # 2:00 PM ET statement
                if start <= ts <= end:
                    out.append(EconomicEvent(ts, "USD", "FOMC Rate Decision", "High"))

        return sorted(out, key=lambda e: e.time_utc)


class ForexFactoryCalendar:
    """
    Live high-impact feed (for the running bot). Fetches the ForexFactory
    community JSON mirror for last/this/next week.
    """

    BASE = "https://nfs.faireconomy.media/ff_calendar_{week}.json"

    def events(self, week: str = "thisweek", min_impact: str = "High") -> list[EconomicEvent]:
        import json
        import urllib.request

        url = self.BASE.format(week=week)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = json.load(r)

        want = {"High"} if min_impact == "High" else {"High", "Medium"}
        out: list[EconomicEvent] = []
        for e in raw:
            if e.get("impact") not in want:
                continue
            ts = pd.Timestamp(e["date"]).tz_convert(UTC)
            out.append(EconomicEvent(ts, e.get("country", "?"), e.get("title", ""), e["impact"]))
        return sorted(out, key=lambda e: e.time_utc)
