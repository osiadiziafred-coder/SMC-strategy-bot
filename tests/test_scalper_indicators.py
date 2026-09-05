import numpy as np
import pandas as pd

from ml_scalper.indicators import atr, candle_parts, ema, rsi, rolling_vwap


def _ohlc(n=80, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.4, n))
    open_ = np.r_[100, close[:-1]]
    high = np.maximum(open_, close) + 0.2
    low = np.minimum(open_, close) - 0.2
    idx = pd.date_range("2024-01-01", periods=n, freq="5min")
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": np.full(n, 100.0),
            "spread": np.full(n, 10.0),
        },
        index=idx,
    )


def test_ema_is_causal_and_finite_after_warmup():
    df = _ohlc()
    e = ema(df["close"], 20)
    assert e.iloc[:19].isna().all()
    assert np.isfinite(e.iloc[19:]).all()


def test_rsi_bounds():
    df = _ohlc()
    r = rsi(df["close"], 14)
    valid = r.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_atr_positive():
    df = _ohlc()
    a = atr(df, 14)
    assert (a.dropna() > 0).all()


def test_vwap_and_candles():
    df = _ohlc()
    v = rolling_vwap(df, 20)
    assert np.isfinite(v).all()
    parts = candle_parts(df)
    assert (parts["range"] > 0).all()
    assert (parts["upper_wick"] >= -1e-9).all()
    assert (parts["lower_wick"] >= -1e-9).all()
