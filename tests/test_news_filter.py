"""Tests for the news calendar + avoid-filter."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.news.calendar import DeterministicUSCalendar  # noqa: E402
from src.news.filter import NewsFilter  # noqa: E402


def test_nfp_always_first_friday():
    cal = DeterministicUSCalendar(include_fomc=False)
    evs = cal.events(pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2024-12-31", tz="UTC"))
    # 12 NFP events in a year, each on a Friday, each in the first 7 days.
    assert len(evs) == 12
    for e in evs:
        assert e.time_utc.day_name() == "Friday"
        assert e.time_utc.day <= 7


def test_dst_shifts_utc_time():
    # NFP is 08:30 ET. Winter (EST) -> 13:30 UTC; summer (EDT) -> 12:30 UTC.
    cal = DeterministicUSCalendar(include_fomc=False)
    jan = cal.events(pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-01-31", tz="UTC"))[0]
    jul = cal.events(pd.Timestamp("2025-07-01", tz="UTC"), pd.Timestamp("2025-07-31", tz="UTC"))[0]
    assert jan.time_utc.hour == 13 and jan.time_utc.minute == 30
    assert jul.time_utc.hour == 12 and jul.time_utc.minute == 30


def test_blackout_flags_bar_containing_event():
    cal = DeterministicUSCalendar(include_fomc=False)
    evs = cal.events(pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-01-31", tz="UTC"))
    # NFP 2025-01-03 13:30 UTC falls inside the H4 bar opening 12:00.
    idx = pd.date_range("2025-01-01", "2025-01-05", freq="4h", tz="UTC")
    nf = NewsFilter(evs, before_minutes=60, after_minutes=60)
    mask = nf.blackout_mask(idx, bar_minutes=240)
    blacked = set(idx[mask])
    assert pd.Timestamp("2025-01-03 12:00", tz="UTC") in blacked


def test_currency_filter():
    cal = DeterministicUSCalendar()
    evs = cal.events(pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-03-31", tz="UTC"))
    # All deterministic events are USD; filtering to EUR removes everything.
    nf_eur = NewsFilter(evs, currencies={"EUR"})
    idx = pd.date_range("2025-01-01", "2025-03-31", freq="4h", tz="UTC")
    assert nf_eur.blackout_mask(idx).sum() == 0
    nf_usd = NewsFilter(evs, currencies={"USD"})
    assert nf_usd.blackout_mask(idx).sum() > 0


def test_empty_events_no_blackout():
    idx = pd.date_range("2025-01-01", "2025-01-05", freq="4h", tz="UTC")
    nf = NewsFilter([], currencies={"USD"})
    assert nf.blackout_mask(idx).sum() == 0
    assert nf.is_blackout(pd.Timestamp("2025-01-03 13:30", tz="UTC")) is False
