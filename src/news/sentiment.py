"""
News headline fetch + lightweight financial sentiment scoring.

INFORMATIONAL ONLY. This is a discretionary "radar" for you, the human - it is
deliberately NOT wired into the bot's automated trade decisions (news-sentiment
auto-trading is unbacktestable and latency-disadvantaged; see docs).

Headlines come from Google News RSS (free, no key). Sentiment is a transparent
finance-tuned lexicon score in [-1, +1]. It's a crude heuristic (upgradable to
an LLM later) and reflects headline TONE, which is NOT the same as future price
direction - treat it as awareness, not a signal.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import pandas as pd

# Finance-tuned tone lexicon (headline vocabulary).
POSITIVE = {
    "rally", "rallies", "surge", "surges", "soar", "soars", "gain", "gains",
    "jump", "jumps", "climb", "climbs", "rise", "rises", "rebound", "rebounds",
    "beat", "beats", "optimism", "bullish", "boost", "strong", "strength",
    "upbeat", "higher", "advance", "advances", "recover", "recovers", "recovery",
    "ease", "eases", "easing", "dovish", "record high", "outperform", "upgrade",
    "demand", "support", "rebounds", "buy",
}
NEGATIVE = {
    "fall", "falls", "drop", "drops", "plunge", "plunges", "slump", "slumps",
    "tumble", "tumbles", "sink", "sinks", "decline", "declines", "loss", "losses",
    "fear", "fears", "war", "conflict", "tension", "tensions", "escalation",
    "escalate", "crisis", "hawkish", "selloff", "sell-off", "weak", "weakness",
    "recession", "sanctions", "attack", "strike", "strikes", "crash", "lower",
    "retreat", "pressure", "worry", "worries", "concern", "concerns",
    "uncertainty", "downgrade", "slowdown", "slows", "risk", "risks", "threat",
}


@dataclass
class Headline:
    title: str
    published: pd.Timestamp | None
    source: str
    score: float


def score_text(text: str) -> float:
    """Tone score in [-1, +1] from the finance lexicon (0 = neutral)."""
    low = text.lower()
    pos = sum(len(re.findall(rf"\b{re.escape(t)}\b", low)) for t in POSITIVE)
    neg = sum(len(re.findall(rf"\b{re.escape(t)}\b", low)) for t in NEGATIVE)
    if pos + neg == 0:
        return 0.0
    return (pos - neg) / (pos + neg)


def fetch_headlines(query: str, within_days: int = 4, limit: int = 20) -> list[Headline]:
    """Fetch recent headlines for a query from Google News RSS."""
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        root = ET.fromstring(r.read())

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=within_days)
    out: list[Headline] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        pub = None
        raw = item.findtext("pubDate")
        if raw:
            try:
                pub = pd.Timestamp(parsedate_to_datetime(raw)).tz_convert("UTC")
            except Exception:
                pub = None
        if pub is not None and pub < cutoff:
            continue
        source = ""
        src_el = item.find("source")
        if src_el is not None and src_el.text:
            source = src_el.text
        out.append(Headline(title, pub, source, score_text(title)))
        if len(out) >= limit:
            break
    return out


def aggregate(headlines: list[Headline]) -> dict:
    """Aggregate tone across headlines."""
    if not headlines:
        return {"tone": 0.0, "n": 0, "pos": 0, "neg": 0, "neutral": 0}
    scores = [h.score for h in headlines]
    pos = sum(1 for s in scores if s > 0.05)
    neg = sum(1 for s in scores if s < -0.05)
    neutral = len(scores) - pos - neg
    return {"tone": sum(scores) / len(scores), "n": len(scores),
            "pos": pos, "neg": neg, "neutral": neutral}


# Search topics per portfolio instrument (kept to 1 query each to limit calls).
INSTRUMENT_QUERIES = {
    "GOLD": "gold price XAU",
    "SILVER": "silver price",
    "NATGAS": "natural gas price",
    "PLATINUM": "platinum price",
    "GBPJPY": "British pound Japanese yen",
    "AUDUSD": "Australian dollar RBA",
    "USDJPY": "Japanese yen Bank of Japan",
    "BRENT": "Brent crude oil price",
    "BTC": "Bitcoin price",
}

# Macro / geopolitical context topics.
MACRO_TOPICS = {
    "Strait of Hormuz": "Strait of Hormuz",
    "Fed / rates": "Federal Reserve interest rate decision",
    "US politics": "Trump economy tariffs",
    "Middle East / oil": "Middle East oil supply",
    "US inflation": "US inflation CPI",
}


def tone_label(tone: float) -> str:
    if tone > 0.15:
        return "POSITIVE tone"
    if tone < -0.15:
        return "NEGATIVE tone"
    return "neutral/mixed"
