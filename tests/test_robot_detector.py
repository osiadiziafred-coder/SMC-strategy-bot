import numpy as np
import pandas as pd

from ml_smc_robot import smc_detector as smc
from ml_smc_robot.config import Config
from ml_smc_robot.mt5_connector import SyntheticConnector


def _data(n=1500):
    cfg = Config()
    conn = SyntheticConnector(cfg, n_m15=n, seed=3)
    conn.connect()
    return conn.get_rates("M15", n)


def test_atr_is_positive_and_finite():
    df = _data()
    atr = smc.atr_series(df, 14).dropna()
    assert (atr > 0).all()
    assert np.isfinite(atr).all()


def test_bos_and_choch_are_causal_signed():
    df = _data()
    bos = smc.bos_series(df, 20)
    choch = smc.choch_series(df, 20)
    assert set(bos.unique()).issubset({-1, 0, 1})
    assert set(choch.unique()).issubset({-1, 0, 1})
    # CHoCH only fires where a BOS fires.
    assert ((choch != 0) <= (bos != 0)).all()


def test_premium_discount_in_unit_range():
    df = _data()
    pd_series = smc.premium_discount_series(df).dropna()
    assert pd_series.between(0.0, 1.0).all()


def test_fair_value_gap_detection():
    rows = [
        [1.0, 1.05, 0.98, 1.02, 100, 20],
        [1.02, 1.20, 1.01, 1.18, 100, 20],
        [1.18, 1.25, 1.10, 1.22, 100, 20],  # low(1.10) > high[0](1.05) => bullish FVG
    ]
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "tick_volume", "spread"])
    gaps = smc.detect_fair_value_gaps(df)
    assert any(g.direction == smc.Direction.BULLISH for g in gaps)
    assert smc.fvg_bullish_size(df).iloc[-1] > 0


def test_analyze_returns_state():
    df = _data()
    state = smc.analyze(df)
    assert isinstance(state, smc.SMCState)
    assert state.bias in (smc.Bias.BULLISH, smc.Bias.BEARISH, smc.Bias.RANGE)
    assert state.atr > 0
