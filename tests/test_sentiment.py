"""Tests for the offline sentiment scorer (no network)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.news.sentiment import score_text, aggregate, Headline, tone_label  # noqa: E402


def test_positive_headline_scores_positive():
    assert score_text("Gold prices rally and surge to record high on strong demand") > 0


def test_negative_headline_scores_negative():
    assert score_text("Oil plunges as war fears and sanctions fuel a market selloff") < 0


def test_neutral_headline_is_zero():
    assert score_text("Central bank holds meeting on Tuesday afternoon") == 0.0


def test_score_bounded():
    for txt in ["surge rally gains boost", "plunge crash war crisis", "the a of to"]:
        s = score_text(txt)
        assert -1.0 <= s <= 1.0


def test_aggregate_counts():
    hs = [Headline("rally surges", None, "", 1.0),
          Headline("plunge crash", None, "", -1.0),
          Headline("meeting held", None, "", 0.0)]
    agg = aggregate(hs)
    assert agg["n"] == 3 and agg["pos"] == 1 and agg["neg"] == 1 and agg["neutral"] == 1
    assert abs(agg["tone"]) < 1e-9


def test_tone_label():
    assert tone_label(0.5) == "POSITIVE tone"
    assert tone_label(-0.5) == "NEGATIVE tone"
    assert tone_label(0.0) == "neutral/mixed"
