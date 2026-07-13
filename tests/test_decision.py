"""Tests for the pure live-trading decision logic."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.risk.position_sizing import SymbolSpec, RiskParams  # noqa: E402
from src.live.decision import decide  # noqa: E402

SPEC = SymbolSpec(tick_size=0.1, tick_value=0.1, volume_min=0.01, volume_step=0.01, volume_max=100.0)
RISK = RiskParams(risk_percent_per_trade=2.0, max_risk_percent_per_trade=5.0)


def _signals(sig: int, atr: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame({"signal": [0, sig], "atr": [atr, atr]})


def test_enter_long_when_flat_and_long_signal():
    d = decide(_signals(1), position_side=0, bid=59999, ask=60001,
               balance=100_000, spec=SPEC, risk=RISK, sl_atr_mult=2.5, tp_rr=2.0)
    assert d.action == "enter"
    assert d.side == 1
    assert d.lots > 0
    # SL below entry, TP above, with 2:1 reward:risk geometry.
    assert d.sl < 60001 < d.tp
    assert d.tp - 60001 == pytest.approx(2 * (60001 - d.sl), rel=1e-6)


def test_enter_short_geometry():
    d = decide(_signals(-1), position_side=0, bid=59999, ask=60001,
               balance=100_000, spec=SPEC, risk=RISK, sl_atr_mult=2.5, tp_rr=2.0)
    assert d.action == "enter" and d.side == -1
    assert d.tp < 59999 < d.sl


def test_blackout_blocks_entry():
    d = decide(_signals(1), position_side=0, bid=59999, ask=60001,
               balance=100_000, spec=SPEC, risk=RISK, sl_atr_mult=2.5, tp_rr=2.0,
               blackout=True)
    assert d.action == "skip"
    assert "news" in d.reason.lower()


def test_no_signal_does_nothing():
    d = decide(_signals(0), position_side=0, bid=59999, ask=60001,
               balance=100_000, spec=SPEC, risk=RISK, sl_atr_mult=2.5, tp_rr=2.0)
    assert d.action == "nothing"


def test_opposite_signal_closes_position():
    # Long open, fresh short signal -> close.
    d = decide(_signals(-1), position_side=1, bid=59999, ask=60001,
               balance=100_000, spec=SPEC, risk=RISK, sl_atr_mult=2.5, tp_rr=2.0)
    assert d.action == "close"


def test_same_direction_holds():
    d = decide(_signals(0), position_side=1, bid=59999, ask=60001,
               balance=100_000, spec=SPEC, risk=RISK, sl_atr_mult=2.5, tp_rr=2.0)
    assert d.action == "hold"


def test_skip_when_too_risky_for_min_lot():
    # Tiny balance -> even min lot risks > 2% -> default policy skips.
    d = decide(_signals(1), position_side=0, bid=59999, ask=60001,
               balance=5.0, spec=SPEC, risk=RISK, sl_atr_mult=2.5, tp_rr=2.0)
    assert d.action == "skip"
