"""Causal technical indicators. No SMC concepts.

All functions are vectorised and use only current-and-past bars (no look-ahead).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def momentum(close: pd.Series, lookback: int = 3) -> pd.Series:
    return close - close.shift(lookback)


def log_return(close: pd.Series, lookback: int = 1) -> pd.Series:
    return np.log(close / close.shift(lookback))


def rolling_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    return log_return(close, 1).rolling(window, min_periods=max(5, window // 2)).std()


def rolling_vwap(df: pd.DataFrame, window: int) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["tick_volume"].replace(0.0, 1.0) if "tick_volume" in df.columns else pd.Series(1.0, index=df.index)
    pv = typical * vol
    return pv.rolling(window, min_periods=1).sum() / vol.rolling(window, min_periods=1).sum()


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP that resets at the calendar day (useful for XAUUSD)."""

    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["tick_volume"].replace(0.0, 1.0) if "tick_volume" in df.columns else pd.Series(1.0, index=df.index)
    if not isinstance(df.index, pd.DatetimeIndex):
        return rolling_vwap(df, 96)
    day = pd.Series(df.index.date, index=df.index)
    pv = (typical * vol).groupby(day).cumsum()
    vv = vol.groupby(day).cumsum().replace(0.0, np.nan)
    return pv / vv


def candle_parts(df: pd.DataFrame) -> pd.DataFrame:
    body = df["close"] - df["open"]
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    upper = df["high"] - pd.concat([df["open"], df["close"]], axis=1).max(axis=1)
    lower = pd.concat([df["open"], df["close"]], axis=1).min(axis=1) - df["low"]
    out = pd.DataFrame(index=df.index)
    out["body"] = body
    out["range"] = rng
    out["upper_wick"] = upper
    out["lower_wick"] = lower
    out["body_ratio"] = body.abs() / rng
    return out


def trend_sign(ema_fast: pd.Series, ema_slow: pd.Series) -> pd.Series:
    diff = ema_fast - ema_slow
    return np.sign(diff).replace(0.0, np.nan).ffill().fillna(0.0)


def trend_strength(ema_fast: pd.Series, ema_slow: pd.Series, atr_s: pd.Series) -> pd.Series:
    return (ema_fast - ema_slow).abs() / atr_s.replace(0.0, np.nan)


def distance_atr(price: pd.Series, level: pd.Series, atr_s: pd.Series) -> pd.Series:
    return (price - level) / atr_s.replace(0.0, np.nan)


def pullback_depth(high: pd.Series, low: pd.Series, close: pd.Series, atr_s: pd.Series, lookback: int = 10) -> pd.Series:
    """Positive when price has retraced from a recent extreme, in ATRs.

    Sign follows the most recent impulse: positive = dip from a high (buy
    pullback), negative = rally from a low (sell pullback).
    """

    recent_high = high.rolling(lookback, min_periods=3).max()
    recent_low = low.rolling(lookback, min_periods=3).min()
    dip = (recent_high - close) / atr_s.replace(0.0, np.nan)
    rally = (close - recent_low) / atr_s.replace(0.0, np.nan)
    # Net pullback: dip minus rally. In a clean buy pullback dip >> rally.
    return dip - rally


def volume_relative(df: pd.DataFrame, window: int = 20) -> pd.Series:
    vol = df["tick_volume"] if "tick_volume" in df.columns else df.get("volume", pd.Series(0.0, index=df.index))
    mean = vol.rolling(window, min_periods=1).mean().replace(0.0, np.nan)
    return vol / mean


def hour_cycle(index: pd.Index) -> tuple[pd.Series, pd.Series]:
    if not isinstance(index, pd.DatetimeIndex):
        z = pd.Series(0.0, index=index)
        return z, z
    hour = pd.Series(index.hour + index.minute / 60.0, index=index)
    ang = 2.0 * np.pi * hour / 24.0
    return np.sin(ang), np.cos(ang)
