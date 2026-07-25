"""
Forex + commodities OHLCV loader (Yahoo Finance public chart API, no auth).

Yahoo covers FX pairs (e.g. EURUSD=X) and commodity futures (e.g. GC=F gold,
CL=F WTI crude, SI=F silver), with many years of daily history - ideal for
robust walk-forward testing on less-volatile-than-crypto markets.

Yahoo does NOT offer a native 4h interval, so for forex/commodities we trade on
the DAILY timeframe (a natural swing horizon) with a weekly trend filter.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pandas as pd

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Friendly name -> (Yahoo symbol, JustMarkets-style symbol, asset class)
INSTRUMENTS = {
    # --- FX majors ---
    "EURUSD": ("EURUSD=X", "EURUSD", "forex"),
    "GBPUSD": ("GBPUSD=X", "GBPUSD", "forex"),
    "USDJPY": ("USDJPY=X", "USDJPY", "forex"),
    "AUDUSD": ("AUDUSD=X", "AUDUSD", "forex"),
    "USDCAD": ("USDCAD=X", "USDCAD", "forex"),
    # --- FX added (majors + crosses) ---
    "USDCHF": ("USDCHF=X", "USDCHF", "forex"),
    "NZDUSD": ("NZDUSD=X", "NZDUSD", "forex"),
    "EURJPY": ("EURJPY=X", "EURJPY", "forex"),
    "GBPJPY": ("GBPJPY=X", "GBPJPY", "forex"),
    "EURGBP": ("EURGBP=X", "EURGBP", "forex"),
    "AUDJPY": ("AUDJPY=X", "AUDJPY", "forex"),
    # --- Commodities ---
    "XAUUSD": ("GC=F", "XAUUSD", "commodity"),   # gold
    "XAGUSD": ("SI=F", "XAGUSD", "commodity"),   # silver
    "WTI":    ("CL=F", "USOIL", "commodity"),    # crude oil
    "BRENT":  ("BZ=F", "UKOIL", "commodity"),    # brent crude
    "NATGAS": ("NG=F", "NGAS", "commodity"),     # natural gas
    "COPPER": ("HG=F", "COPPER", "commodity"),   # copper
    "PLATINUM": ("PL=F", "XPTUSD", "commodity"), # platinum
    # --- Indices (futures continuous) ---
    "SP500":  ("ES=F", "US500", "index"),        # S&P 500
    "NASDAQ": ("NQ=F", "USTEC", "index"),        # Nasdaq 100
    "DOW":    ("YM=F", "US30", "index"),         # Dow 30
    "DAX":    ("^GDAXI", "GER40", "index"),      # DAX 40
    "NIKKEI": ("^N225", "JP225", "index"),       # Nikkei 225
}

# Crypto handled via the OKX loader (real volume, 24/7): logical -> OKX instId.
CRYPTO_INSTRUMENTS = {
    "BTC": "BTC-USDT",
    "ETH": "ETH-USDT",
    "SOL": "SOL-USDT",
}

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data_cache")


def fetch_yahoo_ohlcv(
    yahoo_symbol: str,
    interval: str = "1d",
    years: int = 15,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Fetch daily OHLCV for a Yahoo symbol over the last `years` years.

    Uses explicit period1/period2 unix bounds (NOT range=max, which silently
    downsamples long ranges to monthly bars).

    Returns a DataFrame indexed by UTC timestamp with columns
    open, high, low, close, volume (oldest -> newest).
    """
    import time as _time

    os.makedirs(_CACHE_DIR, exist_ok=True)
    safe = yahoo_symbol.replace("=", "").replace("^", "").replace("/", "")
    cache_path = os.path.join(_CACHE_DIR, f"yahoo_{safe}_{interval}.csv")

    if use_cache and os.path.exists(cache_path):
        return pd.read_csv(cache_path, parse_dates=["timestamp"], index_col="timestamp")

    period2 = int(_time.time())
    period1 = period2 - int(years * 365.25 * 24 * 3600)
    url = YAHOO_URL.format(symbol=urllib.parse.quote(yahoo_symbol))
    url += f"?interval={interval}&period1={period1}&period2={period2}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)

    result = payload["chart"]["result"]
    if not result:
        raise RuntimeError(f"No data for {yahoo_symbol}: {payload['chart'].get('error')}")
    res = result[0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]

    df = pd.DataFrame({
        "timestamp": pd.to_datetime(ts, unit="s", utc=True),
        "open": q["open"],
        "high": q["high"],
        "low": q["low"],
        "close": q["close"],
        "volume": q.get("volume", [0] * len(ts)),
    })
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")
    df.to_csv(cache_path)
    return df


def fetch_yahoo_h4(yahoo_symbol: str, days: int = 729, use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch hourly data (Yahoo caps ~729 days) and resample to a 4-hour timeframe.

    Gives ~2 years of H4 bars for forex/commodities - an apples-to-apples match
    with the crypto H4 setup, and far more trades than daily.
    """
    import time as _time

    os.makedirs(_CACHE_DIR, exist_ok=True)
    safe = yahoo_symbol.replace("=", "").replace("^", "").replace("/", "")
    cache_path = os.path.join(_CACHE_DIR, f"yahoo_{safe}_4h.csv")
    if use_cache and os.path.exists(cache_path):
        return pd.read_csv(cache_path, parse_dates=["timestamp"], index_col="timestamp")

    period2 = int(_time.time())
    period1 = period2 - int(days * 24 * 3600)
    url = YAHOO_URL.format(symbol=urllib.parse.quote(yahoo_symbol))
    url += f"?interval=1h&period1={period1}&period2={period2}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)

    res = payload["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    hourly = pd.DataFrame({
        "timestamp": pd.to_datetime(res["timestamp"], unit="s", utc=True),
        "open": q["open"], "high": q["high"], "low": q["low"],
        "close": q["close"], "volume": q.get("volume", [0] * len(res["timestamp"])),
    }).dropna(subset=["open", "high", "low", "close"])
    hourly = hourly.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")

    # Resample 1h -> 4h. Drop empty buckets (weekends/holidays leave gaps).
    h4 = hourly.resample("4h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"])

    h4.to_csv(cache_path)
    return h4


if __name__ == "__main__":
    for name, (ysym, _, cls) in INSTRUMENTS.items():
        try:
            d = fetch_yahoo_ohlcv(ysym)
            h4 = fetch_yahoo_h4(ysym)
            print(f"{name:8} ({cls:9}) daily={len(d):>5}  H4={len(h4):>5}  "
                  f"H4 range {h4.index[0].date()} -> {h4.index[-1].date()}")
        except Exception as e:
            print(f"{name:8} FAILED: {e!r}")
