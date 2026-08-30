import pandas as pd
import pytest

from smc_bot.data import SyntheticConfig, generate_synthetic, load_csv, validate_ohlc


def test_generate_synthetic_is_reproducible():
    a = generate_synthetic(SyntheticConfig(n=200, seed=42))
    b = generate_synthetic(SyntheticConfig(n=200, seed=42))
    pd.testing.assert_frame_equal(a, b)


def test_generate_synthetic_respects_ohlc_invariants():
    df = generate_synthetic(SyntheticConfig(n=500, seed=1))
    assert len(df) == 500
    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()


def test_validate_ohlc_rejects_bad_candles():
    bad = pd.DataFrame({"open": [1.0], "high": [0.9], "low": [0.8], "close": [0.95]})
    with pytest.raises(ValueError):
        validate_ohlc(bad)


def test_load_csv_roundtrip(tmp_path):
    df = generate_synthetic(SyntheticConfig(n=50, seed=3))
    csv_path = tmp_path / "candles.csv"
    df.to_csv(csv_path)
    loaded = load_csv(csv_path)
    assert list(loaded.columns) == ["open", "high", "low", "close"]
    assert len(loaded) == 50


def test_load_csv_missing_columns(tmp_path):
    csv_path = tmp_path / "bad.csv"
    pd.DataFrame({"open": [1.0], "high": [1.1]}).to_csv(csv_path, index=False)
    with pytest.raises(ValueError):
        load_csv(csv_path)
