"""
Historical OHLCV data loader.

Pulls candles from the OKX public API (no auth required) and caches them to CSV
so we don't re-download every run.

Why OKX? Binance is geo-blocked in this environment, and OKX exposes plenty of
history with simple pagination. OKX BTC-USDT spot closely tracks the same market
as a JustMarkets BTCUSD CFD, so it is a good proxy for STRATEGY DEVELOPMENT.
Exact fills/spreads get validated later on a JustMarkets demo account.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional

import pandas as pd

OKX_HISTORY_URL = "https://www.okx.com/api/v5/market/history-candles"

# OKX bar codes for a few timeframes we care about.
BAR_MAP = {"H1": "1H", "H4": "4H", "D1": "1D", "M15": "15m"}

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data_cache")


def _fetch_page(inst_id: str, bar: str, after_ms: Optional[int]) -> list:
    url = f"{OKX_HISTORY_URL}?instId={inst_id}&bar={bar}&limit=100"
    if after_ms is not None:
        url += f"&after={after_ms}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX error: {payload.get('msg')} (code {payload.get('code')})")
    return payload["data"]


def fetch_okx_ohlcv(
    inst_id: str = "BTC-USDT",
    timeframe: str = "H4",
    bars: int = 4000,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Fetch up to `bars` candles for `inst_id` at the given timeframe.

    Returns a DataFrame indexed by UTC timestamp with columns:
        open, high, low, close, volume   (sorted oldest -> newest)
    """
    bar = BAR_MAP.get(timeframe)
    if bar is None:
        raise ValueError(f"Unsupported timeframe {timeframe!r}. Use one of {list(BAR_MAP)}")

    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_CACHE_DIR, f"{inst_id.replace('-', '')}_{timeframe}.csv")

    if use_cache and os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["timestamp"], index_col="timestamp")
        if len(df) >= bars:
            return df.tail(bars)

    rows: list = []
    after_ms: Optional[int] = None
    while len(rows) < bars:
        page = _fetch_page(inst_id, bar, after_ms)
        if not page:
            break
        rows.extend(page)
        # OKX returns newest-first; paginate older using the OLDEST ts we have.
        after_ms = int(page[-1][0])
        time.sleep(0.15)  # be polite to the public API

    if not rows:
        raise RuntimeError("No data returned from OKX.")

    df = pd.DataFrame(
        [r[:6] for r in rows],
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")

    df.to_csv(cache_path)
    return df.tail(bars)


if __name__ == "__main__":
    d = fetch_okx_ohlcv(bars=200)
    print(f"Fetched {len(d)} bars: {d.index[0]} -> {d.index[-1]}")
    print(d.tail())
