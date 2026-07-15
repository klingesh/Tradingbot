"""
News filter (avoid mode).

Given a set of high-impact events, decide which bars are inside a "blackout"
window - a period around each event when we don't want to open new trades
(and optionally want to be flat), because price can gap violently.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .calendar import EconomicEvent, UTC


class NewsFilter:
    def __init__(
        self,
        events: list[EconomicEvent],
        before_minutes: int = 120,
        after_minutes: int = 120,
        currencies: set[str] | None = None,
    ):
        """
        Parameters
        ----------
        events         : high-impact events to avoid.
        before_minutes : start of the blackout, before each event.
        after_minutes  : end of the blackout, after each event.
        currencies     : if given, only events for these currencies count
                         (e.g. {"USD"} for gold/silver, {"USD","JPY"} for USDJPY).
        """
        if currencies is not None:
            events = [e for e in events if e.currency in currencies]
        # Store event times as naive-UTC datetime64 (avoids tz-aware vs naive
        # comparison errors in numpy).
        self._event_times = np.array(
            sorted(e.time_utc.tz_convert(UTC).tz_localize(None).to_datetime64() for e in events),
            dtype="datetime64[ns]",
        )
        self.before = np.timedelta64(before_minutes, "m")
        self.after = np.timedelta64(after_minutes, "m")

    @staticmethod
    def _to_naive_utc64(t: pd.Timestamp) -> np.datetime64:
        ts = pd.Timestamp(t)
        ts = ts.tz_convert(UTC) if ts.tzinfo else ts.tz_localize(UTC)
        return ts.tz_localize(None).to_datetime64()

    def is_blackout(self, t: pd.Timestamp) -> bool:
        if self._event_times.size == 0:
            return False
        t64 = self._to_naive_utc64(t)
        lo = self._event_times - self.before
        hi = self._event_times + self.after
        return bool(np.any((t64 >= lo) & (t64 <= hi)))

    def blackout_mask(self, index: pd.DatetimeIndex, bar_minutes: int = 240) -> np.ndarray:
        """
        Boolean array aligned to `index`: True for a bar if a high-impact event
        occurs anywhere from `before` minutes before the bar OPENS until `after`
        minutes after the bar CLOSES. `bar_minutes` is the timeframe (H4 = 240).

        Accounting for bar duration matters: on H4 a bar spans 4 hours, so an
        event could land hours into a bar we're about to enter.
        """
        if self._event_times.size == 0:
            return np.zeros(len(index), dtype=bool)

        idx = index.tz_convert(UTC) if index.tz is not None else index.tz_localize(UTC)
        bar_times = idx.tz_localize(None).to_numpy().astype("datetime64[ns]")
        bar_td = np.timedelta64(bar_minutes, "m")

        # Bar open t is blocked if some event e satisfies:
        #   t - before <= e <= t + bar + after
        # i.e. t in [e - bar - after, e + before]. Per event window on the
        # bar-open axis:
        lo = self._event_times - bar_td - self.after
        hi = self._event_times + self.before

        # Blackout iff (#windows started by t) > (#windows already ended before t).
        lo_sorted = np.sort(lo)
        hi_sorted = np.sort(hi)
        started = np.searchsorted(lo_sorted, bar_times, side="right")
        ended = np.searchsorted(hi_sorted, bar_times, side="left")
        return started > ended
