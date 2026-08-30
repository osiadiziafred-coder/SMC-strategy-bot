"""Smart Money Concepts (SMC) detection for XAUUSD multi-timeframe analysis.

This module provides two complementary APIs:

* **Vectorised per-bar series** (``*_series`` functions) used to build a
  consistent ML feature matrix across thousands of historical bars. They are
  strictly *causal* - every value at bar ``t`` depends only on data up to and
  including ``t`` - which prevents look-ahead bias/leakage in the features.
* **Object-level detection** (:func:`analyze`, :func:`detect_order_blocks`,
  :func:`detect_fair_value_gaps`, ...) used by the live brain for the trade gate,
  stop-loss anchoring and human-readable logging/explainability.

Concepts implemented: swing highs/lows, market trend/bias, Break of Structure
(BOS), Market Structure Shift (MSS), Change of Character (CHoCH), order blocks,
fair value gaps, liquidity sweeps, equal highs/lows, liquidity zones,
premium/discount (equilibrium), candle displacement, ATR/volatility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NONE = "none"


class Bias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGE = "RANGE"


@dataclass(frozen=True)
class SwingPoint:
    index: int
    price: float
    kind: str  # "high" | "low"


@dataclass(frozen=True)
class Zone:
    kind: str            # "order_block" | "fvg" | "liquidity"
    direction: Direction
    top: float
    bottom: float
    index: int

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def height(self) -> float:
        return max(self.top - self.bottom, 0.0)

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass
class SMCState:
    """Summary of the SMC picture on a single timeframe at the last bar."""

    bias: Bias = Bias.RANGE
    trend: int = 0                 # +1 up, -1 down, 0 range
    bos: int = 0                   # +1 bullish BOS, -1 bearish BOS
    mss: int = 0                   # +1/-1 market structure shift (with displacement)
    choch: int = 0                 # +1/-1 change of character
    liquidity_sweep: int = 0       # +1 bullish sweep (swept lows), -1 bearish
    displacement: float = 0.0      # last candle body / ATR
    atr: float = 0.0
    volatility: float = 0.0
    premium_discount: float = 0.5  # 0=range low (discount), 1=range high (premium)
    equal_highs: bool = False
    equal_lows: bool = False
    price: float = 0.0
    swing_high: float = np.nan
    swing_low: float = np.nan
    nearest_bull_ob: Zone | None = None
    nearest_bear_ob: Zone | None = None
    nearest_bull_fvg: Zone | None = None
    nearest_bear_fvg: Zone | None = None
    liquidity_levels: list[float] = field(default_factory=list)

    def as_log_dict(self) -> dict:
        return {
            "bias": self.bias.value,
            "bos": self.bos,
            "mss": self.mss,
            "choch": self.choch,
            "sweep": self.liquidity_sweep,
            "premium_discount": round(self.premium_discount, 3),
            "atr": round(self.atr, 3),
        }


# ---------------------------------------------------------------------------
# Basic vectorised building blocks
# ---------------------------------------------------------------------------
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def trend_series(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    """+1 uptrend, -1 downtrend, 0 range based on EMA relationship and slope."""

    ema_fast = ema(df["close"], fast)
    ema_slow = ema(df["close"], slow)
    slope = ema_fast.diff()
    up = (ema_fast > ema_slow) & (slope > 0)
    down = (ema_fast < ema_slow) & (slope < 0)
    out = pd.Series(0, index=df.index, dtype=int)
    out[up] = 1
    out[down] = -1
    return out


def rolling_swing_high(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Highest high over the previous ``lookback`` bars (causal, excludes now)."""

    return df["high"].shift(1).rolling(lookback, min_periods=1).max()


def rolling_swing_low(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    return df["low"].shift(1).rolling(lookback, min_periods=1).min()


def momentum_series(df: pd.DataFrame, period: int = 10) -> pd.Series:
    return df["close"] - df["close"].shift(period)


def volatility_series(df: pd.DataFrame, period: int = 20) -> pd.Series:
    returns = df["close"].pct_change()
    return returns.rolling(period, min_periods=2).std()


def premium_discount_series(df: pd.DataFrame, lookback: int = 50) -> pd.Series:
    """Position of close within the recent range: 0 = discount low, 1 = premium high."""

    hi = df["high"].rolling(lookback, min_periods=2).max()
    lo = df["low"].rolling(lookback, min_periods=2).min()
    rng = (hi - lo).replace(0, np.nan)
    pos = (df["close"] - lo) / rng
    return pos.clip(0.0, 1.0)


def bos_series(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Break of Structure: +1 when close breaks the prior swing high, -1 the low."""

    sh = rolling_swing_high(df, lookback)
    sl = rolling_swing_low(df, lookback)
    out = pd.Series(0, index=df.index, dtype=int)
    out[df["close"] > sh] = 1
    out[df["close"] < sl] = -1
    return out


def displacement_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Signed candle body size normalised by ATR (impulsive move strength)."""

    body = df["close"] - df["open"]
    atr = atr_series(df, period).replace(0, np.nan)
    return (body / atr).fillna(0.0)


def _choch_from_bos(bos: pd.Series) -> pd.Series:
    """Change of Character: first structural break against the running trend."""

    out = np.zeros(len(bos), dtype=int)
    running = 0
    bos_vals = bos.to_numpy()
    for i, b in enumerate(bos_vals):
        if b != 0 and running != 0 and b != running:
            out[i] = b  # break against the established trend
        if b != 0:
            running = b
    return pd.Series(out, index=bos.index)


def choch_series(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    return _choch_from_bos(bos_series(df, lookback))


def mss_series(df: pd.DataFrame, lookback: int = 20, disp_threshold: float = 1.0) -> pd.Series:
    """Market Structure Shift: a CHoCH confirmed by a displacement candle."""

    choch = choch_series(df, lookback).to_numpy()
    disp = displacement_series(df).to_numpy()
    out = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        if choch[i] > 0 and disp[i] >= disp_threshold:
            out[i] = 1
        elif choch[i] < 0 and disp[i] <= -disp_threshold:
            out[i] = -1
    return pd.Series(out, index=df.index)


def liquidity_sweep_series(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """+1 when price wicks below the prior low then closes back above it (bullish
    sweep of sell-side liquidity); -1 for the mirror bearish sweep."""

    prev_low = rolling_swing_low(df, lookback)
    prev_high = rolling_swing_high(df, lookback)
    out = pd.Series(0, index=df.index, dtype=int)
    bull = (df["low"] < prev_low) & (df["close"] > prev_low)
    bear = (df["high"] > prev_high) & (df["close"] < prev_high)
    out[bull] = 1
    out[bear] = -1
    return out


def fvg_bullish_size(df: pd.DataFrame) -> pd.Series:
    """Size of a bullish 3-candle fair value gap ending at each bar (0 if none)."""

    gap = df["low"] - df["high"].shift(2)
    return gap.clip(lower=0.0).fillna(0.0)


def fvg_bearish_size(df: pd.DataFrame) -> pd.Series:
    gap = df["low"].shift(2) - df["high"]
    return gap.clip(lower=0.0).fillna(0.0)


def _distance_to_last_opposite_candle(df: pd.DataFrame, bullish: bool) -> pd.Series:
    """Causal distance from close to the most recent opposite-colour candle's
    mid-price - a proxy for order-block distance."""

    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    dist = np.full(n, np.nan)
    last_ob_mid = np.nan
    for i in range(n):
        if not np.isnan(last_ob_mid):
            dist[i] = abs(closes[i] - last_ob_mid)
        # Update AFTER computing distance so bar t only sees OBs up to t-1..t.
        is_bearish = closes[i] < opens[i]
        is_bullish = closes[i] > opens[i]
        if bullish and is_bearish:
            last_ob_mid = (highs[i] + lows[i]) / 2.0
        elif (not bullish) and is_bullish:
            last_ob_mid = (highs[i] + lows[i]) / 2.0
    return pd.Series(dist, index=df.index)


def order_block_distance_series(df: pd.DataFrame) -> pd.Series:
    """Minimum distance to the nearest bullish/bearish order-block proxy."""

    bull = _distance_to_last_opposite_candle(df, bullish=True)
    bear = _distance_to_last_opposite_candle(df, bullish=False)
    return pd.concat([bull, bear], axis=1).min(axis=1)


# ---------------------------------------------------------------------------
# Object-level detection (for the live decision gate + logging)
# ---------------------------------------------------------------------------
def find_swings(df: pd.DataFrame, lookback: int = 3) -> list[SwingPoint]:
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    swings: list[SwingPoint] = []
    for i in range(lookback, n - lookback):
        wh = highs[i - lookback : i + lookback + 1]
        wl = lows[i - lookback : i + lookback + 1]
        if highs[i] == wh.max() and (wh == highs[i]).sum() == 1:
            swings.append(SwingPoint(i, float(highs[i]), "high"))
        elif lows[i] == wl.min() and (wl == lows[i]).sum() == 1:
            swings.append(SwingPoint(i, float(lows[i]), "low"))
    return swings


def detect_order_blocks(df: pd.DataFrame, lookback: int = 20, max_zones: int = 5) -> list[Zone]:
    """Order block = last opposite-colour candle before a BOS displacement."""

    bos = bos_series(df, lookback)
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    zones: list[Zone] = []
    for i in np.where(bos.to_numpy() != 0)[0]:
        direction = Direction.BULLISH if bos.iloc[i] > 0 else Direction.BEARISH
        for j in range(i, -1, -1):
            down = closes[j] < opens[j]
            up = closes[j] > opens[j]
            if direction == Direction.BULLISH and down:
                zones.append(Zone("order_block", direction, float(highs[j]), float(lows[j]), j))
                break
            if direction == Direction.BEARISH and up:
                zones.append(Zone("order_block", direction, float(highs[j]), float(lows[j]), j))
                break
    return zones[-max_zones:]


def detect_fair_value_gaps(df: pd.DataFrame, max_zones: int = 5) -> list[Zone]:
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    zones: list[Zone] = []
    for i in range(2, len(df)):
        if highs[i - 2] < lows[i]:
            zones.append(Zone("fvg", Direction.BULLISH, float(lows[i]), float(highs[i - 2]), i))
        elif lows[i - 2] > highs[i]:
            zones.append(Zone("fvg", Direction.BEARISH, float(lows[i - 2]), float(highs[i]), i))
    return zones[-max_zones:]


def detect_equal_levels(df: pd.DataFrame, lookback: int = 30, tol_frac: float = 0.0006):
    """Return (equal_highs, equal_lows, liquidity_levels) from recent swings."""

    window = df.iloc[-lookback:] if len(df) > lookback else df
    swings = find_swings(window, lookback=2)
    highs = [s.price for s in swings if s.kind == "high"]
    lows = [s.price for s in swings if s.kind == "low"]
    ref = float(df["close"].iloc[-1]) or 1.0
    tol = ref * tol_frac

    def _has_equal(levels: list[float]) -> bool:
        for a in range(len(levels)):
            for b in range(a + 1, len(levels)):
                if abs(levels[a] - levels[b]) <= tol:
                    return True
        return False

    liquidity_levels = sorted(set(round(x, 3) for x in highs + lows))
    return _has_equal(highs), _has_equal(lows), liquidity_levels


def market_bias(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> Bias:
    t = int(trend_series(df, fast, slow).iloc[-1])
    if t > 0:
        return Bias.BULLISH
    if t < 0:
        return Bias.BEARISH
    return Bias.RANGE


def _nearest_zone(zones: list[Zone], price: float, direction: Direction) -> Zone | None:
    candidates = [z for z in zones if z.direction == direction]
    if not candidates:
        return None
    return min(candidates, key=lambda z: abs(z.mid - price))


def analyze(df: pd.DataFrame, atr_period: int = 14, swing_lookback: int = 20) -> SMCState:
    """Produce an :class:`SMCState` summarising the last bar of ``df``."""

    if df is None or len(df) < swing_lookback + 5:
        return SMCState()

    price = float(df["close"].iloc[-1])
    atr = float(atr_series(df, atr_period).iloc[-1])
    obs = detect_order_blocks(df, swing_lookback)
    fvgs = detect_fair_value_gaps(df)
    eq_highs, eq_lows, liq_levels = detect_equal_levels(df)

    state = SMCState(
        bias=market_bias(df),
        trend=int(trend_series(df).iloc[-1]),
        bos=int(bos_series(df, swing_lookback).iloc[-1]),
        mss=int(mss_series(df, swing_lookback).iloc[-1]),
        choch=int(choch_series(df, swing_lookback).iloc[-1]),
        liquidity_sweep=int(liquidity_sweep_series(df, swing_lookback).iloc[-1]),
        displacement=float(displacement_series(df, atr_period).iloc[-1]),
        atr=atr,
        volatility=float(volatility_series(df).iloc[-1]),
        premium_discount=float(premium_discount_series(df).iloc[-1]),
        equal_highs=eq_highs,
        equal_lows=eq_lows,
        price=price,
        swing_high=float(rolling_swing_high(df, swing_lookback).iloc[-1]),
        swing_low=float(rolling_swing_low(df, swing_lookback).iloc[-1]),
        nearest_bull_ob=_nearest_zone(obs, price, Direction.BULLISH),
        nearest_bear_ob=_nearest_zone(obs, price, Direction.BEARISH),
        nearest_bull_fvg=_nearest_zone(fvgs, price, Direction.BULLISH),
        nearest_bear_fvg=_nearest_zone(fvgs, price, Direction.BEARISH),
        liquidity_levels=liq_levels,
    )
    return state
