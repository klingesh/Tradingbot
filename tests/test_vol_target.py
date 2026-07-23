"""Tests for the volatility-targeting scalar."""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.risk.vol_target import volatility_target_scalar  # noqa: E402


def _series_low_then_high(seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    low = rng.normal(0, 0.001, 300)    # calm regime
    high = rng.normal(0, 0.02, 100)    # volatile regime
    rets = np.concatenate([low, high])
    price = 100 * np.exp(np.cumsum(rets))
    return pd.Series(price)


def test_shape_and_clamp():
    close = _series_low_then_high()
    s = volatility_target_scalar(close, lookback=20, median_window=100,
                                 min_scale=0.5, max_scale=1.5)
    assert s.shape[0] == len(close)
    assert np.all(s >= 0.5 - 1e-9) and np.all(s <= 1.5 + 1e-9)


def test_derisks_in_high_vol():
    close = _series_low_then_high()
    # median_window spans the calm history, so the volatile tail is measured
    # against the calmer norm and gets de-risked.
    s = volatility_target_scalar(close, lookback=20, median_window=300,
                                 min_scale=0.5, max_scale=1.5)
    # During the volatile tail, risk should be scaled DOWN (< 1).
    assert np.mean(s[-50:]) < 1.0
    assert s[-1] < 1.0


def test_no_lookahead():
    # Changing only the FINAL close must not alter ANY scalar value, because
    # scalar[i] is computed strictly from data up to bar i-1.
    close = _series_low_then_high()
    s1 = volatility_target_scalar(close)
    tampered = close.copy()
    tampered.iloc[-1] *= 1.5
    s2 = volatility_target_scalar(tampered)
    assert np.allclose(s1, s2, equal_nan=True)


def test_warmup_defaults_to_one():
    close = _series_low_then_high()
    s = volatility_target_scalar(close, lookback=20)
    # Early bars (before enough history) default to a neutral 1.0.
    assert s[0] == 1.0
