"""ML + SMC trading robot - single-file edition (default symbol: Volatility 75 Index).

This is a *consolidated* build of the modular ``ml_smc_robot`` package: every
Python module (config, MT5/synthetic/CSV connectors, SMC detector, feature
engineering, the real ML model, risk manager, command bridge, logging, the
training pipeline and the live brain) merged into one file for easy copying.

It is behaviour-identical to the package. The MQL5 side stays separate (a
different language): ``mql5/SMC_Safety_Bridge.mq5``.

Architecture:

    MT5 data -> SMC detection (H1 bias / M30 confirm / M15 entry)
             -> feature engineering -> trained ML model -> BUY/SELL probability
             -> SMC validation + risk management -> command.json -> MQL5 bridge

The Python side only ever *proposes* trades by writing ``command.json``; the
MQL5 EA validates and executes, and independently manages one-position
protection, breakeven and trailing stops even if Python disconnects.

Usage (offline, no terminal required)::

    # 1) Train the model on synthetic data (time-ordered split, no look-ahead)
    python ml_smc_robot_all_in_one.py train --source synthetic --bars 80000

    # 2) Print a full multi-timeframe SMC readout for the current bar
    python ml_smc_robot_all_in_one.py run --source synthetic --analyze

    # 3) Dry-run the full pipeline over an offline feed (writes command.json)
    python ml_smc_robot_all_in_one.py run --source synthetic --replay 3000

Live (Windows + MetaTrader 5)::

    python ml_smc_robot_all_in_one.py train --source mt5 --bars 30000
    python ml_smc_robot_all_in_one.py run --source mt5 \
        --bridge-dir "C:\\Users\\<you>\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files\\smc_bridge"

Dependencies: numpy, pandas, scikit-learn, lightgbm (optional: xgboost),
joblib. On Windows the MetaTrader5 package enables live data/execution; on
Linux/macOS it is skipped and the offline synthetic/CSV providers are used.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


# ===========================================================================
# config
# ===========================================================================
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR
DEFAULT_MODEL_DIR = PACKAGE_DIR / "models"
DEFAULT_LOG_DIR = PACKAGE_DIR / "logs"

# For offline testing the bridge lives inside the project. In production this
# MUST point at the MetaTrader 5 terminal's shared folder, e.g. the terminal
# *Common* folder ``...\\Terminal\\Common\\Files\\smc_bridge`` when the EA opens
# files with FILE_COMMON (the default in the shipped EA).
DEFAULT_BRIDGE_DIR = PROJECT_DIR / "smc_bridge"


# Per-symbol market characteristics. ``start_price``/``vol``/``spread_range`` are
# only used by the offline synthetic feed; ``point``/``digits``/lot fields are
# broker facts also used live (the real MT5 terminal overrides them when
# connected). Volatility 75 Index (Deriv synthetic index) trades 24/7 with high
# volatility; XAUUSDm is kept as an available preset.
SYMBOL_PRESETS: dict[str, dict] = {
    "Volatility 75 Index": {
        "start_price": 100_000.0,
        "vol": 0.0020,
        "spread_range": (20.0, 60.0),
        "point": 0.01,
        "digits": 2,
        "min_lot": 0.001,
        "lot_step": 0.001,
        "max_lot": 50.0,
        "contract_size": 1.0,
    },
    "XAUUSDm": {
        "start_price": 2_300.0,
        "vol": 0.0011,
        "spread_range": (18.0, 42.0),
        "point": 0.01,
        "digits": 2,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
        "contract_size": 100.0,
    },
}

DEFAULT_SYMBOL_PRESET = SYMBOL_PRESETS["Volatility 75 Index"]


@dataclass
class Config:
    # --- Market -----------------------------------------------------------
    symbol: str = "Volatility 75 Index"
    bias_timeframe: str = "H1"        # major market bias
    confirm_timeframe: str = "M30"    # structure confirmation
    entry_timeframe: str = "M15"      # entry / setup timeframe

    live_bars: int = 400              # bars per timeframe when analysing live
    train_bars: int = 20_000          # bars per timeframe when training

    # --- Machine learning -------------------------------------------------
    model_backends: tuple[str, ...] = ("lightgbm", "xgboost", "random_forest")
    ml_min_confidence: float = 0.70   # ML_MIN_CONFIDENCE
    model_dir: Path = field(default_factory=lambda: DEFAULT_MODEL_DIR)
    model_filename: str = "smc_model.joblib"

    # Label engineering (triple-barrier). SL distance = atr * atr_sl_mult.
    label_horizon: int = 16           # bars ahead to resolve TP/SL
    atr_period: int = 14
    atr_sl_mult: float = 1.5          # SL distance in ATRs used for labelling

    # --- Risk / trade management -----------------------------------------
    risk_reward: float = 2.0          # 1:2
    max_open_positions: int = 1
    lot_per_balance: float = 100.0    # lot = balance / lot_per_balance * lot_unit
    lot_unit: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01

    breakeven_r: float = 1.0          # move SL to BE at +1R
    breakeven_buffer_points: float = 20.0
    trail_start_r: float = 1.5        # activate trailing at +1.5R
    trail_distance_atr: float = 1.0   # trailing distance in ATRs
    trail_enabled: bool = True

    # --- Safety gates -----------------------------------------------------
    max_spread_points: float = 60.0
    min_sl_distance_points: float = 50.0
    point: float = 0.01               # set from preset
    digits: int = 2                   # set from preset

    # --- Bridge / heartbeat ----------------------------------------------
    bridge_dir: Path = field(default_factory=lambda: DEFAULT_BRIDGE_DIR)
    command_filename: str = "command.json"
    status_filename: str = "status.json"
    heartbeat_interval_sec: float = 5.0
    python_timeout_sec: float = 30.0
    poll_interval_sec: float = 2.0

    # --- Data source ------------------------------------------------------
    data_source: str = "mt5"          # "mt5" | "synthetic" | "csv"
    csv_dir: Path = field(default_factory=lambda: PROJECT_DIR / "data")

    # --- Logging ----------------------------------------------------------
    log_dir: Path = field(default_factory=lambda: DEFAULT_LOG_DIR)
    log_level: str = "INFO"

    def __post_init__(self):
        # Apply symbol-intrinsic broker facts from the preset. Environment
        # overrides (Config.from_env) are applied afterwards and still win.
        preset = SYMBOL_PRESETS.get(self.symbol)
        if preset:
            self.point = preset["point"]
            self.digits = preset["digits"]
            self.min_lot = preset["min_lot"]
            self.lot_step = preset["lot_step"]
            self.max_lot = preset["max_lot"]

    def symbol_preset(self) -> dict:
        return SYMBOL_PRESETS.get(self.symbol, DEFAULT_SYMBOL_PRESET)

    @property
    def model_path(self) -> Path:
        return self.model_dir / self.model_filename

    @property
    def command_path(self) -> Path:
        return self.bridge_dir / self.command_filename

    @property
    def status_path(self) -> Path:
        return self.bridge_dir / self.status_filename

    @property
    def timeframes(self) -> list[str]:
        return [self.bias_timeframe, self.confirm_timeframe, self.entry_timeframe]

    def ensure_dirs(self) -> None:
        for d in (self.model_dir, self.log_dir, self.bridge_dir):
            Path(d).mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Path):
                d[k] = str(v)
        return d

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        """Build a config, applying ``SMC_``-prefixed environment overrides."""

        cfg = cls(**overrides)
        for f in cfg.__dataclass_fields__.values():  # type: ignore[attr-defined]
            env_key = f"SMC_{f.name.upper()}"
            if env_key not in os.environ:
                continue
            raw = os.environ[env_key]
            current = getattr(cfg, f.name)
            try:
                if isinstance(current, bool):
                    setattr(cfg, f.name, raw.strip().lower() in {"1", "true", "yes", "on"})
                elif isinstance(current, int):
                    setattr(cfg, f.name, int(raw))
                elif isinstance(current, float):
                    setattr(cfg, f.name, float(raw))
                elif isinstance(current, Path):
                    setattr(cfg, f.name, Path(raw))
                else:
                    setattr(cfg, f.name, raw)
            except (TypeError, ValueError):
                pass
        return cfg


# ===========================================================================
# logging_utils
# ===========================================================================
def setup_logger(cfg: Config, name: str = "smc_brain") -> logging.Logger:
    cfg.ensure_dirs()
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    file_handler = logging.FileHandler(Path(cfg.log_dir) / "smc_brain.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def format_decision_line(
    symbol: str,
    h1_bias: str,
    m30_confirm: str,
    m15_setup: str,
    bos: int,
    mss: int,
    choch: int,
    sweep: int,
    eq_sweep: int,
    ob: bool,
    fvg: bool,
    ml_buy: float,
    ml_sell: float,
    decision: str,
) -> str:
    return (
        f"{symbol} | H1={h1_bias} | M30={m30_confirm} | M15={m15_setup} | "
        f"BOS={bos} | MSS={mss} | CHoCH={choch} | Sweep={bool(sweep)} | "
        f"EqSweep={bool(eq_sweep)} | OB={ob} | FVG={fvg} | "
        f"ML_BUY={ml_buy:.2f} | ML_SELL={ml_sell:.2f} | Decision={decision}"
    )


def format_explanation(explain: list[tuple[str, float, float]]) -> str:
    parts = [f"{name}(val={value:.3f}, contrib={contrib:+.3f})" for name, value, contrib in explain]
    return "Explain: " + ", ".join(parts)


def _sign_tag(value: int, pos: str, neg: str) -> str:
    if value > 0:
        return pos
    if value < 0:
        return neg
    return "-"


def _zone_tag(zone) -> str:
    if zone is None:
        return "none"
    return f"{zone.bottom:.2f}-{zone.top:.2f}"


def format_smc_report(symbol: str, states: dict, tick: dict | None = None) -> str:
    """Full multi-timeframe SMC readout: Bias, BOS, MSS, CHoCH, Liquidity sweep,
    Equal-liquidity sweep, Order Block and FVG per timeframe."""

    lines = []
    lines.append("=" * 100)
    title = f"SMC ANALYSIS  |  {symbol}"
    if tick is not None:
        title += f"  |  price={tick.get('bid', float('nan')):.2f}  spread={tick.get('spread_points', 0):.0f}pts"
    lines.append(title)
    lines.append("=" * 100)
    header = (
        f"{'TF':<5} {'Bias':<8} {'BOS':<5} {'CHoCH':<6} {'MSS':<5} "
        f"{'LiqSweep':<10} {'EqLiqSweep':<11} {'OrderBlock':<22} {'FVG':<22}"
    )
    lines.append(header)
    lines.append("-" * 100)
    for tf, s in states.items():
        ob = s.nearest_bull_ob or s.nearest_bear_ob
        fvg = s.nearest_bull_fvg or s.nearest_bear_fvg
        ob_dir = "BULL " if s.nearest_bull_ob else ("BEAR " if s.nearest_bear_ob else "")
        fvg_dir = "BULL " if s.nearest_bull_fvg else ("BEAR " if s.nearest_bear_fvg else "")
        lines.append(
            f"{tf:<5} {s.bias.value:<8} "
            f"{_sign_tag(s.bos, 'UP', 'DOWN'):<5} "
            f"{_sign_tag(s.choch, 'UP', 'DOWN'):<6} "
            f"{_sign_tag(s.mss, 'UP', 'DOWN'):<5} "
            f"{_sign_tag(s.liquidity_sweep, 'BULL', 'BEAR'):<10} "
            f"{_sign_tag(s.equal_liquidity_sweep, 'BULL', 'BEAR'):<11} "
            f"{(ob_dir + _zone_tag(ob)):<22} "
            f"{(fvg_dir + _zone_tag(fvg)):<22}"
        )
    lines.append("=" * 100)
    return "\n".join(lines)


# ===========================================================================
# smc_detector
# ===========================================================================
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
    equal_liquidity_sweep: int = 0 # +1 swept equal lows, -1 swept equal highs
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
            "equal_liquidity_sweep": self.equal_liquidity_sweep,
            "premium_discount": round(self.premium_discount, 3),
            "atr": round(self.atr, 3),
        }


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


def equal_liquidity_sweep_series(df: pd.DataFrame, lookback: int = 30, tol_frac: float = 0.0006) -> pd.Series:
    """Sweep of *equal* highs/lows (a resting liquidity pool).

    Equal highs/lows (two or more prior extremes at the same price within a
    tolerance) attract liquidity. A sweep occurs when price runs through that
    equal level and then closes back on the other side:

    * -1 bearish equal-liquidity sweep: equal highs are taken out then price
      closes back below (buy-side liquidity grabbed).
    * +1 bullish equal-liquidity sweep: equal lows are taken out then price
      closes back above (sell-side liquidity grabbed).

    Computed causally: bar ``i`` only inspects the ``lookback`` bars before it.
    """

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    n = len(df)
    out = np.zeros(n, dtype=int)
    for i in range(lookback, n):
        wh = highs[i - lookback:i]
        wl = lows[i - lookback:i]
        hi_level = wh.max()
        lo_level = wl.min()
        eq_high = np.sum(np.abs(wh - hi_level) <= hi_level * tol_frac) >= 2
        eq_low = np.sum(np.abs(wl - lo_level) <= lo_level * tol_frac) >= 2
        if eq_high and highs[i] > hi_level and closes[i] < hi_level:
            out[i] = -1
        elif eq_low and lows[i] < lo_level and closes[i] > lo_level:
            out[i] = 1
    return pd.Series(out, index=df.index)


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
        equal_liquidity_sweep=int(equal_liquidity_sweep_series(df).iloc[-1]),
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


# ===========================================================================
# mt5_connector
# ===========================================================================
_TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
OHLCV_COLUMNS = ["open", "high", "low", "close", "tick_volume", "spread"]


class BaseConnector:
    def connect(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def shutdown(self) -> None:  # pragma: no cover - interface
        pass

    def get_rates(self, timeframe: str, count: int) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    def get_tick(self, symbol: str) -> dict:  # pragma: no cover
        raise NotImplementedError

    def symbol_info(self, symbol: str) -> dict:  # pragma: no cover
        raise NotImplementedError

    def account_info(self) -> dict:  # pragma: no cover
        raise NotImplementedError

    def common_files_path(self) -> Path | None:
        return None


class MT5Connector(BaseConnector):
    """Real MetaTrader 5 terminal API (Windows). Live data + execution feed."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._mt5 = None

    def _lib(self):
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except Exception as exc:  # pragma: no cover - platform dependent
                raise RuntimeError(
                    "MetaTrader5 package is unavailable (Windows-only). Use "
                    "data_source='synthetic' or 'csv' for offline training/testing."
                ) from exc
            self._mt5 = mt5
        return self._mt5

    def _tf_const(self, timeframe: str):
        mt5 = self._lib()
        return getattr(mt5, f"TIMEFRAME_{timeframe}")

    def connect(self) -> bool:  # pragma: no cover - requires terminal
        mt5 = self._lib()
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")
        if not mt5.symbol_select(self.cfg.symbol, True):
            raise RuntimeError(f"Could not select symbol {self.cfg.symbol}")
        return True

    def shutdown(self) -> None:  # pragma: no cover - requires terminal
        if self._mt5 is not None:
            self._mt5.shutdown()

    def get_rates(self, timeframe: str, count: int) -> pd.DataFrame:  # pragma: no cover
        mt5 = self._lib()
        rates = mt5.copy_rates_from_pos(self.cfg.symbol, self._tf_const(timeframe), 0, count)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"No rates returned for {self.cfg.symbol} {timeframe}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
        if "spread" not in df.columns:
            df["spread"] = 0.0
        cols = [c for c in OHLCV_COLUMNS if c in df.columns]
        return df[cols].astype(float)

    def get_tick(self, symbol: str) -> dict:  # pragma: no cover
        mt5 = self._lib()
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        point = info.point if info else self.cfg.point
        spread_points = (tick.ask - tick.bid) / point if point else 0.0
        return {"bid": tick.bid, "ask": tick.ask, "spread_points": spread_points, "time": tick.time}

    def symbol_info(self, symbol: str) -> dict:  # pragma: no cover
        mt5 = self._lib()
        info = mt5.symbol_info(symbol)
        return {
            "point": info.point,
            "digits": info.digits,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_contract_size": info.trade_contract_size,
        }

    def account_info(self) -> dict:  # pragma: no cover
        mt5 = self._lib()
        acc = mt5.account_info()
        return {"balance": acc.balance, "equity": acc.equity, "currency": acc.currency}

    def common_files_path(self) -> Path | None:  # pragma: no cover
        mt5 = self._lib()
        info = mt5.terminal_info()
        if info and getattr(info, "commondata_path", None):
            return Path(info.commondata_path) / "Files" / "smc_bridge"
        return None


class SyntheticConnector(BaseConnector):
    """Deterministic offline generator producing self-consistent H1/M30/M15
    candles (M30/H1 aggregated from M15), parametrised per symbol preset."""

    def __init__(self, cfg: Config, n_m15: int | None = None, seed: int = 7, balance: float = 1000.0):
        self.cfg = cfg
        self.seed = seed
        self._balance = balance
        needed = max(cfg.train_bars, cfg.live_bars) * 4 + 500
        self.n_m15 = int(n_m15 or max(needed, 8000))
        self._cache: dict[str, pd.DataFrame] = {}
        self._cutoff_time = None  # replay support: only expose bars up to this time

    def connect(self) -> bool:
        self._build()
        return True

    def timeline(self) -> pd.DatetimeIndex:
        """M15 timestamps, useful for replaying the live pipeline bar-by-bar."""

        self._build()
        return self._cache["M15"].index

    def set_cutoff_time(self, ts) -> None:
        """Restrict all timeframes to bars at or before ``ts`` (replay mode)."""

        self._cutoff_time = ts

    def _build(self) -> None:
        if self._cache:
            return
        rng = np.random.default_rng(self.seed)
        n = self.n_m15
        preset = self.cfg.symbol_preset()
        start_price = preset["start_price"]
        vol = preset["vol"]
        spread_lo, spread_hi = preset["spread_range"]
        # Regime-switching drift produces realistic trends and ranges. The drift
        # amplitude is scaled with volatility (relative to a 0.0011 baseline) so
        # the learnable trend/momentum signal keeps a comparable signal-to-noise
        # ratio across symbols with very different volatilities.
        drift_scale = vol / 0.0011
        # ~40 trend regimes across the series. Short regimes (each ~n/40 bars)
        # give the trend/SMC features a clear, learnable direction while keeping
        # the drift's *integral* (its effect on the price level) bounded.
        phase = np.linspace(0.0, 80.0 * np.pi, n)
        drift = (0.00060 * np.sin(phase) + 0.00020 * np.sin(phase * 0.25)) * drift_scale
        shocks = rng.normal(0.0, vol, n)
        # AR(1) momentum gives the SMC/trend features genuine (learnable) value.
        # A gentle Ornstein-Uhlenbeck pull toward the starting log-price keeps
        # the level bounded over long series and adds a real mean-reversion
        # signal the model can exploit (premium/discount).
        phi = 0.32
        kappa = 3.0e-4
        log_start = np.log(start_price)
        logp = np.empty(n)
        logp[0] = log_start
        lr_prev = drift[0] + shocks[0]
        for t in range(1, n):
            pull = -kappa * (logp[t - 1] - log_start)
            lr = phi * lr_prev + drift[t] + pull + shocks[t]
            logp[t] = logp[t - 1] + lr
            lr_prev = lr
        close = np.exp(logp)

        open_ = np.empty(n)
        open_[0] = start_price
        open_[1:] = close[:-1]
        body_hi = np.maximum(open_, close)
        body_lo = np.minimum(open_, close)
        up_wick = np.abs(rng.normal(0.0, vol * 0.7, n)) * close
        dn_wick = np.abs(rng.normal(0.0, vol * 0.7, n)) * close
        high = body_hi + up_wick
        low = body_lo - dn_wick
        tick_volume = rng.integers(80, 600, n).astype(float)
        spread = np.round(rng.uniform(spread_lo, spread_hi, n))  # points

        index = pd.date_range("2023-01-01", periods=n, freq="15min", name="time")
        m15 = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": tick_volume,
                "spread": spread,
            },
            index=index,
        ).round(3)
        self._cache["M15"] = m15
        self._cache["M30"] = self._resample(m15, "30min")
        self._cache["H1"] = self._resample(m15, "60min")

    @staticmethod
    def _resample(m15: pd.DataFrame, rule: str) -> pd.DataFrame:
        agg = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "tick_volume": "sum",
            "spread": "mean",
        }
        out = m15.resample(rule, label="right", closed="right").agg(agg).dropna()
        return out.round(3)

    def get_rates(self, timeframe: str, count: int) -> pd.DataFrame:
        self._build()
        if timeframe not in self._cache:
            raise ValueError(f"Unsupported timeframe {timeframe}")
        df = self._cache[timeframe]
        if self._cutoff_time is not None:
            df = df[df.index <= self._cutoff_time]
        return df.iloc[-count:].copy()

    def get_tick(self, symbol: str) -> dict:
        self._build()
        last = self.get_rates("M15", 1).iloc[-1]
        point = self.cfg.point
        spread_points = float(last["spread"])
        bid = float(last["close"])
        ask = bid + spread_points * point
        return {"bid": bid, "ask": ask, "spread_points": spread_points, "time": None}

    def symbol_info(self, symbol: str) -> dict:
        preset = self.cfg.symbol_preset()
        return {
            "point": self.cfg.point,
            "digits": self.cfg.digits,
            "volume_min": self.cfg.min_lot,
            "volume_max": self.cfg.max_lot,
            "volume_step": self.cfg.lot_step,
            "trade_contract_size": preset.get("contract_size", 1.0),
        }

    def account_info(self) -> dict:
        return {"balance": self._balance, "equity": self._balance, "currency": "USD"}


class CSVConnector(BaseConnector):
    """Reads previously exported ``<symbol>_<TF>.csv`` files."""

    def __init__(self, cfg: Config, balance: float = 1000.0):
        self.cfg = cfg
        self._balance = balance

    def connect(self) -> bool:
        return True

    def get_rates(self, timeframe: str, count: int) -> pd.DataFrame:
        path = Path(self.cfg.csv_dir) / f"{self.cfg.symbol}_{timeframe}.csv"
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {path}")
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]
        time_col = next((c for c in ("time", "date", "datetime", "timestamp") if c in df.columns), None)
        if time_col:
            df[time_col] = pd.to_datetime(df[time_col])
            df = df.set_index(time_col).sort_index()
        if "spread" not in df.columns:
            df["spread"] = 0.0
        if "tick_volume" not in df.columns:
            df["tick_volume"] = df.get("volume", 0.0)
        return df[[c for c in OHLCV_COLUMNS if c in df.columns]].astype(float).iloc[-count:]

    def get_tick(self, symbol: str) -> dict:
        df = self.get_rates(self.cfg.entry_timeframe, 1)
        bid = float(df["close"].iloc[-1])
        spread_points = float(df["spread"].iloc[-1]) if "spread" in df else 0.0
        return {"bid": bid, "ask": bid + spread_points * self.cfg.point, "spread_points": spread_points, "time": None}

    def symbol_info(self, symbol: str) -> dict:
        preset = self.cfg.symbol_preset()
        return {
            "point": self.cfg.point,
            "digits": self.cfg.digits,
            "volume_min": self.cfg.min_lot,
            "volume_max": self.cfg.max_lot,
            "volume_step": self.cfg.lot_step,
            "trade_contract_size": preset.get("contract_size", 1.0),
        }

    def account_info(self) -> dict:
        return {"balance": self._balance, "equity": self._balance, "currency": "USD"}


def make_connector(cfg: Config, **kwargs) -> BaseConnector:
    """Return the connector configured by ``cfg.data_source``."""

    source = (cfg.data_source or "mt5").lower()
    if source == "mt5":
        return MT5Connector(cfg)
    if source == "synthetic":
        return SyntheticConnector(cfg, **kwargs)
    if source == "csv":
        return CSVConnector(cfg, **kwargs)
    raise ValueError(f"Unknown data_source: {cfg.data_source}")


# ===========================================================================
# features
# ===========================================================================
BASE_FEATURES: list[str] = [
    "h1_trend",
    "m30_trend",
    "m15_trend",
    "m15_bos",
    "m15_mss",
    "m15_choch",
    "m15_sweep",
    "m15_eq_liq_sweep",
    "m15_ob_distance",
    "m15_fvg_distance",
    "m15_fvg_size",
    "m15_liq_distance",
    "m15_swing_high_dist",
    "m15_swing_low_dist",
    "m15_atr",
    "spread",
    "m15_body",
    "m15_range",
    "m15_volume",
    "m15_momentum",
    "m15_volatility",
    "m15_premium_discount",
    "m15_recent_move",
    "mtf_alignment",
]

DIRECTION_FEATURES: list[str] = [
    "direction",
    "trend_dir_align",
    "struct_dir_align",
    "pd_dir",
    "momentum_dir",
    "sweep_dir",
    "eq_liq_sweep_dir",
]

FEATURE_COLUMNS: list[str] = BASE_FEATURES + DIRECTION_FEATURES


def _sanitize(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)


def compute_context_features(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Trend/structure context for a higher timeframe (H1/M30)."""

    out = pd.DataFrame(index=df.index)
    out[f"{prefix}_trend"] = trend_series(df)
    out[f"{prefix}_bos"] = bos_series(df)
    out[f"{prefix}_choch"] = choch_series(df)
    out[f"{prefix}_premium_discount"] = premium_discount_series(df)
    return out


def compute_entry_features(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Full SMC feature set for the entry (M15) timeframe, ATR-normalised."""

    atr = atr_series(df, cfg.atr_period)
    atr_safe = atr.replace(0, np.nan)
    close = df["close"]

    swing_high = rolling_swing_high(df)
    swing_low = rolling_swing_low(df)

    out = pd.DataFrame(index=df.index)
    out["m15_trend"] = trend_series(df)
    out["m15_bos"] = bos_series(df)
    out["m15_mss"] = mss_series(df)
    out["m15_choch"] = choch_series(df)
    out["m15_sweep"] = liquidity_sweep_series(df)
    out["m15_eq_liq_sweep"] = equal_liquidity_sweep_series(df)
    out["m15_ob_distance"] = order_block_distance_series(df) / atr_safe
    fvg_bull = fvg_bullish_size(df)
    fvg_bear = fvg_bearish_size(df)
    out["m15_fvg_size"] = (fvg_bull + fvg_bear) / atr_safe
    # Distance to the most recent gap (0 when the current bar forms one).
    has_gap = (fvg_bull + fvg_bear) > 0
    bars_since_gap = (~has_gap).groupby(has_gap.cumsum()).cumcount()
    out["m15_fvg_distance"] = bars_since_gap.astype(float)
    out["m15_liq_distance"] = (
        pd.concat([(swing_high - close).abs(), (close - swing_low).abs()], axis=1).min(axis=1)
        / atr_safe
    )
    out["m15_swing_high_dist"] = (swing_high - close) / atr_safe
    out["m15_swing_low_dist"] = (close - swing_low) / atr_safe
    out["m15_atr"] = atr / close
    out["spread"] = df["spread"] if "spread" in df.columns else 0.0
    out["m15_body"] = (df["close"] - df["open"]).abs() / atr_safe
    out["m15_range"] = (df["high"] - df["low"]) / atr_safe
    vol = df["tick_volume"] if "tick_volume" in df.columns else df.get("volume", pd.Series(0.0, index=df.index))
    out["m15_volume"] = vol / vol.rolling(20, min_periods=1).mean().replace(0, np.nan)
    out["m15_momentum"] = momentum_series(df) / atr_safe
    out["m15_volatility"] = volatility_series(df)
    out["m15_premium_discount"] = premium_discount_series(df)
    out["m15_recent_move"] = (close - close.shift(5)) / atr_safe
    return out


def build_base_matrix(h1: pd.DataFrame, m30: pd.DataFrame, m15: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Assemble the direction-independent feature matrix aligned to M15 bars."""

    entry = compute_entry_features(m15, cfg)
    ctx_h1 = compute_context_features(h1, "h1")
    ctx_m30 = compute_context_features(m30, "m30")

    # Align higher-timeframe context to each M15 bar using the last *closed*
    # higher-timeframe bar (backward as-of join) to avoid look-ahead.
    entry = entry.sort_index()
    merged = pd.merge_asof(
        entry,
        ctx_h1[["h1_trend"]].sort_index(),
        left_index=True,
        right_index=True,
        direction="backward",
    )
    merged = pd.merge_asof(
        merged,
        ctx_m30[["m30_trend"]].sort_index(),
        left_index=True,
        right_index=True,
        direction="backward",
    )

    merged["mtf_alignment"] = (
        np.sign(merged["h1_trend"]) + np.sign(merged["m30_trend"]) + np.sign(merged["m15_trend"])
    )

    merged = merged[BASE_FEATURES]
    return _sanitize(merged)


def add_direction_features(base: pd.DataFrame, direction: int) -> pd.DataFrame:
    """Append direction (+1 BUY / -1 SELL) and interaction features."""

    if direction not in (1, -1):
        raise ValueError("direction must be +1 (BUY) or -1 (SELL)")

    out = base.copy()
    out["direction"] = float(direction)
    out["trend_dir_align"] = out["mtf_alignment"] * direction
    out["struct_dir_align"] = (out["m15_bos"] + out["m15_choch"] + out["m15_mss"]) * direction
    # For a BUY, being in discount (pd < 0.5) is favourable; mirror for SELL.
    out["pd_dir"] = direction * (0.5 - out["m15_premium_discount"])
    out["momentum_dir"] = out["m15_momentum"] * direction
    out["sweep_dir"] = out["m15_sweep"] * direction
    out["eq_liq_sweep_dir"] = out["m15_eq_liq_sweep"] * direction
    return _sanitize(out[FEATURE_COLUMNS])


def triple_barrier_labels(
    df: pd.DataFrame,
    atr: pd.Series,
    direction: int,
    horizon: int,
    atr_sl_mult: float,
    risk_reward: float,
) -> pd.Series:
    """Label each bar 1 if a ``direction`` trade hits TP before SL within
    ``horizon`` bars, else 0. Uses only *future* bars for the label (correct
    supervised labelling) while features remain causal."""

    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    atr_v = atr.to_numpy()
    n = len(df)
    labels = np.full(n, np.nan)

    for i in range(n - horizon):
        sl_dist = atr_v[i] * atr_sl_mult
        if not np.isfinite(sl_dist) or sl_dist <= 0:
            continue
        entry = close[i]
        if direction == 1:
            sl, tp = entry - sl_dist, entry + risk_reward * sl_dist
        else:
            sl, tp = entry + sl_dist, entry - risk_reward * sl_dist

        outcome = 0
        for j in range(i + 1, i + 1 + horizon):
            if direction == 1:
                if low[j] <= sl:
                    outcome = 0
                    break
                if high[j] >= tp:
                    outcome = 1
                    break
            else:
                if high[j] >= sl:
                    outcome = 0
                    break
                if low[j] <= tp:
                    outcome = 1
                    break
        labels[i] = outcome

    return pd.Series(labels, index=df.index)


def build_training_dataset(
    h1: pd.DataFrame, m30: pd.DataFrame, m15: pd.DataFrame, cfg: Config
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return (X, y, timestamps) with BUY and SELL rows stacked in time order."""

    base = build_base_matrix(h1, m30, m15, cfg)
    atr = atr_series(m15, cfg.atr_period)

    frames_X, frames_y, times = [], [], []
    for direction in (1, -1):
        X_dir = add_direction_features(base, direction)
        y_dir = triple_barrier_labels(
            m15, atr, direction, cfg.label_horizon, cfg.atr_sl_mult, cfg.risk_reward
        )
        valid = y_dir.notna()
        frames_X.append(X_dir[valid])
        frames_y.append(y_dir[valid].astype(int))
        times.append(pd.Series(X_dir.index[valid], index=X_dir.index[valid]))

    X = pd.concat(frames_X)
    y = pd.concat(frames_y)
    ts = pd.concat(times)

    # Sort by time so the time-ordered split never mixes future into the past.
    order = np.argsort(ts.to_numpy(), kind="stable")
    X = X.iloc[order].reset_index(drop=True)
    y = y.iloc[order].reset_index(drop=True)
    ts = ts.iloc[order].reset_index(drop=True)
    return X, y, ts


def build_live_features(h1: pd.DataFrame, m30: pd.DataFrame, m15: pd.DataFrame, cfg: Config):
    """Return (base_last_row_df, buy_features_df, sell_features_df) for the last M15 bar."""

    base = build_base_matrix(h1, m30, m15, cfg)
    last = base.iloc[[-1]]
    buy = add_direction_features(last, 1)
    sell = add_direction_features(last, -1)
    return last, buy, sell


# ===========================================================================
# ml_model
# ===========================================================================
def _make_estimator(backends: tuple[str, ...]):
    """Return (estimator, backend_name) for the first importable backend."""

    for backend in backends:
        if backend == "lightgbm":
            try:
                from lightgbm import LGBMClassifier

                return (
                    LGBMClassifier(
                        n_estimators=400,
                        learning_rate=0.05,
                        num_leaves=31,
                        max_depth=-1,
                        subsample=0.8,
                        subsample_freq=1,
                        colsample_bytree=0.8,
                        reg_lambda=1.0,
                        random_state=42,
                        n_jobs=-1,
                        verbosity=-1,
                    ),
                    "lightgbm",
                )
            except Exception:
                continue
        if backend == "xgboost":
            try:
                from xgboost import XGBClassifier

                return (
                    XGBClassifier(
                        n_estimators=400,
                        learning_rate=0.05,
                        max_depth=5,
                        subsample=0.8,
                        colsample_bytree=0.8,
                        reg_lambda=1.0,
                        random_state=42,
                        n_jobs=-1,
                        eval_metric="logloss",
                        tree_method="hist",
                    ),
                    "xgboost",
                )
            except Exception:
                continue
        if backend == "random_forest":
            from sklearn.ensemble import RandomForestClassifier

            return (
                RandomForestClassifier(
                    n_estimators=400,
                    max_depth=None,
                    min_samples_leaf=20,
                    max_features="sqrt",
                    random_state=42,
                    n_jobs=-1,
                    class_weight="balanced_subsample",
                ),
                "random_forest",
            )
    raise RuntimeError("No supported ML backend available")


@dataclass
class MLModel:
    """Real supervised classifier (LightGBM > XGBoost > RandomForest fallback)."""

    feature_names: list[str]
    backends: tuple[str, ...] = ("lightgbm", "xgboost", "random_forest")
    estimator: object = None
    backend: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.estimator is None:
            self.estimator, self.backend = _make_estimator(tuple(self.backends))

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "MLModel":
        self.estimator.fit(X[self.feature_names].to_numpy(), np.asarray(y))
        return self

    def predict_success_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Probability of the positive class (setup success)."""

        proba = self.estimator.predict_proba(X[self.feature_names].to_numpy())
        classes = list(getattr(self.estimator, "classes_", [0, 1]))
        pos_idx = classes.index(1) if 1 in classes else proba.shape[1] - 1
        return proba[:, pos_idx]

    def feature_importance(self) -> dict[str, float]:
        importances = getattr(self.estimator, "feature_importances_", None)
        if importances is None:
            return {}
        total = float(np.sum(importances)) or 1.0
        return {
            name: float(imp) / total
            for name, imp in sorted(
                zip(self.feature_names, importances), key=lambda kv: kv[1], reverse=True
            )
        }

    def explain(self, X_row: pd.DataFrame, top_k: int = 6) -> list[tuple[str, float, float]]:
        """Top contributing features for a single prediction as
        (feature, value, contribution). Uses LightGBM SHAP contributions when
        available, otherwise importance-weighted feature values."""

        row = X_row[self.feature_names].iloc[0]
        contributions: dict[str, float] = {}

        if self.backend == "lightgbm":
            try:
                contrib = self.estimator.predict(
                    X_row[self.feature_names].to_numpy(), pred_contrib=True
                )[0]
                for name, c in zip(self.feature_names, contrib[:-1]):  # last col = bias
                    contributions[name] = float(c)
            except Exception:
                contributions = {}

        if not contributions:
            imp = self.feature_importance()
            contributions = {name: imp.get(name, 0.0) * float(row[name]) for name in self.feature_names}

        ranked = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_k]
        return [(name, float(row[name]), float(contrib)) for name, contrib in ranked]

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "estimator": self.estimator,
            "feature_names": self.feature_names,
            "backend": self.backend,
            "metadata": {**self.metadata, "saved_at": time.time()},
        }
        joblib.dump(payload, path)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "MLModel":
        payload = joblib.load(Path(path))
        return cls(
            feature_names=payload["feature_names"],
            estimator=payload["estimator"],
            backend=payload.get("backend", ""),
            metadata=payload.get("metadata", {}),
        )


# ===========================================================================
# risk_manager
# ===========================================================================
@dataclass
class TradePlan:
    direction: str          # "BUY" | "SELL"
    entry: float
    sl: float
    tp: float
    lots: float
    risk_distance: float
    reward_distance: float
    rr: float
    breakeven_r: float
    trail_start_r: float
    trail_enabled: bool

    def as_log_dict(self) -> dict:
        return {
            "entry": self.entry,
            "sl": self.sl,
            "tp": self.tp,
            "lots": self.lots,
            "rr": round(self.rr, 2),
        }


class RiskManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def normalize_lot(self, lot: float, symbol_info: dict) -> float:
        step = symbol_info.get("volume_step", self.cfg.lot_step) or self.cfg.lot_step
        vmin = symbol_info.get("volume_min", self.cfg.min_lot)
        vmax = symbol_info.get("volume_max", self.cfg.max_lot)
        steps = math.floor(lot / step + 1e-9)
        lot = steps * step
        lot = max(vmin, min(vmax, lot))
        decimals = max(0, int(round(-math.log10(step)))) if step > 0 else 2
        return round(lot, decimals)

    def lot_size(self, balance: float, symbol_info: dict) -> float:
        raw = (balance / self.cfg.lot_per_balance) * self.cfg.lot_unit
        return self.normalize_lot(raw, symbol_info)

    def compute_sl_tp(self, direction: str, entry: float, state: SMCState, symbol_info: dict) -> tuple[float, float, float]:
        point = symbol_info.get("point", self.cfg.point) or self.cfg.point
        digits = symbol_info.get("digits", 2)
        buffer = self.cfg.breakeven_buffer_points * point

        atr = state.atr if state.atr and state.atr > 0 else entry * 0.001
        atr_risk = max(atr * self.cfg.atr_sl_mult, self.cfg.min_sl_distance_points * point)

        if direction == "BUY":
            anchors = [a for a in (state.swing_low, getattr(state.nearest_bull_ob, "bottom", None)) if a]
            structural_sl = (min(anchors) - buffer) if anchors else (entry - atr_risk)
            risk = entry - structural_sl
            if risk <= 0 or risk > 3 * atr_risk:
                risk = atr_risk
            sl = entry - risk
            tp = entry + self.cfg.risk_reward * risk
        else:  # SELL
            anchors = [a for a in (state.swing_high, getattr(state.nearest_bear_ob, "top", None)) if a]
            structural_sl = (max(anchors) + buffer) if anchors else (entry + atr_risk)
            risk = structural_sl - entry
            if risk <= 0 or risk > 3 * atr_risk:
                risk = atr_risk
            sl = entry + risk
            tp = entry - self.cfg.risk_reward * risk

        return round(sl, digits), round(tp, digits), abs(entry - sl)

    def validate_rr(self, direction: str, entry: float, sl: float, tp: float, tol: float = 0.25) -> bool:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk <= 0:
            return False
        rr = reward / risk
        return abs(rr - self.cfg.risk_reward) <= tol

    def check_spread(self, spread_points: float) -> bool:
        return spread_points <= self.cfg.max_spread_points

    def can_open(self, open_positions: int) -> bool:
        return open_positions < self.cfg.max_open_positions

    def build_trade_plan(self, direction: str, entry: float, state: SMCState, symbol_info: dict, balance: float) -> TradePlan:
        sl, tp, risk = self.compute_sl_tp(direction, entry, state, symbol_info)
        lots = self.lot_size(balance, symbol_info)
        reward = abs(tp - entry)
        rr = reward / risk if risk > 0 else 0.0
        return TradePlan(
            direction=direction,
            entry=round(entry, symbol_info.get("digits", 2)),
            sl=sl,
            tp=tp,
            lots=lots,
            risk_distance=risk,
            reward_distance=reward,
            rr=rr,
            breakeven_r=self.cfg.breakeven_r,
            trail_start_r=self.cfg.trail_start_r,
            trail_enabled=self.cfg.trail_enabled,
        )


# ===========================================================================
# command_manager
# ===========================================================================
VALID_ACTIONS = {"BUY", "SELL", "MODIFY", "CLOSE", "HEARTBEAT", "NONE"}


class CommandManager:
    """File-based command bridge: Python writes command.json, EA writes status.json."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.bridge_dir = Path(cfg.bridge_dir)
        self.bridge_dir.mkdir(parents=True, exist_ok=True)
        self._seq = 0
        self._last_signature: tuple | None = None
        self._last_signature_time = 0.0

    def _atomic_write(self, path: Path, obj: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2)
        os.replace(tmp, path)

    def _read_json(self, path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _new_envelope(self, action: str) -> dict:
        self._seq += 1
        now = time.time()
        return {
            "id": uuid.uuid4().hex,
            "seq": self._seq,
            "action": action,
            "symbol": self.cfg.symbol,
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)),
            "heartbeat": now,
        }

    def write_trade_command(self, action: str, lots: float, sl: float, tp: float,
                            entry: float, breakeven_r: float, trail_start_r: float,
                            trail_enabled: bool) -> dict:
        if action not in ("BUY", "SELL"):
            raise ValueError("write_trade_command only supports BUY/SELL")
        cmd = self._new_envelope(action)
        cmd.update(
            {
                "lots": round(float(lots), 2),
                "entry": round(float(entry), 3),
                "sl": round(float(sl), 3),
                "tp": round(float(tp), 3),
                "breakeven_r": float(breakeven_r),
                "trail_start_r": float(trail_start_r),
                "trail_enabled": bool(trail_enabled),
            }
        )
        self._atomic_write(self.cfg.command_path, cmd)
        return cmd

    def write_simple_command(self, action: str, **extra) -> dict:
        if action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {action}")
        cmd = self._new_envelope(action)
        cmd.update(extra)
        self._atomic_write(self.cfg.command_path, cmd)
        return cmd

    def send_heartbeat(self) -> dict:
        """Refresh liveness. If a command already exists, only its heartbeat is
        updated (id preserved) so a pending trade is not lost or re-executed."""

        existing = self._read_json(self.cfg.command_path)
        if existing:
            existing["heartbeat"] = time.time()
            self._atomic_write(self.cfg.command_path, existing)
            return existing
        return self.write_simple_command("HEARTBEAT")

    touch_heartbeat = send_heartbeat  # alias used by the live loop for clarity

    def _signature(self, direction: str, entry: float, sl: float) -> tuple:
        return (direction, round(entry, 1), round(sl, 1))

    def should_send(self, direction: str, entry: float, sl: float, cooldown_sec: float = 300.0) -> bool:
        sig = self._signature(direction, entry, sl)
        now = time.time()
        if sig == self._last_signature and (now - self._last_signature_time) < cooldown_sec:
            return False
        return True

    def mark_sent(self, direction: str, entry: float, sl: float) -> None:
        self._last_signature = self._signature(direction, entry, sl)
        self._last_signature_time = time.time()

    def read_status(self) -> dict:
        return self._read_json(self.cfg.status_path)

    def open_positions(self, status: dict | None = None) -> int:
        status = status if status is not None else self.read_status()
        positions = status.get("positions", [])
        return len([p for p in positions if p.get("symbol") == self.cfg.symbol])

    def is_ea_alive(self, status: dict | None = None) -> bool:
        status = status if status is not None else self.read_status()
        hb = status.get("heartbeat")
        if hb is None:
            return False
        return (time.time() - float(hb)) <= self.cfg.python_timeout_sec


# ===========================================================================
# train_model
# ===========================================================================
def _safe_auc(y_true, y_score) -> float:
    from sklearn.metrics import roc_auc_score

    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def load_history(cfg: Config, connector) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    connector.connect()
    h1 = connector.get_rates(cfg.bias_timeframe, cfg.train_bars)
    m30 = connector.get_rates(cfg.confirm_timeframe, cfg.train_bars)
    m15 = connector.get_rates(cfg.entry_timeframe, cfg.train_bars)
    return h1, m30, m15


def time_ordered_split(X: pd.DataFrame, y: pd.Series, test_frac: float) -> tuple:
    n = len(X)
    split = int(n * (1.0 - test_frac))
    return X.iloc[:split], X.iloc[split:], y.iloc[:split], y.iloc[split:]


def cross_validate(X: pd.DataFrame, y: pd.Series, cfg: Config, n_splits: int) -> dict:
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import TimeSeriesSplit

    tscv = TimeSeriesSplit(n_splits=n_splits)
    aucs, accs = [], []
    for train_idx, val_idx in tscv.split(X):
        if len(np.unique(y.iloc[train_idx])) < 2:
            continue
        model = MLModel(feature_names=FEATURE_COLUMNS, backends=cfg.model_backends)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        proba = model.predict_success_proba(X.iloc[val_idx])
        aucs.append(_safe_auc(y.iloc[val_idx], proba))
        accs.append(accuracy_score(y.iloc[val_idx], (proba >= 0.5).astype(int)))
    return {
        "cv_auc_mean": float(np.nanmean(aucs)) if aucs else float("nan"),
        "cv_auc_std": float(np.nanstd(aucs)) if aucs else float("nan"),
        "cv_accuracy_mean": float(np.mean(accs)) if accs else float("nan"),
        "cv_folds": len(aucs),
    }


def train(cfg: Config, test_frac: float = 0.2, n_splits: int = 4, seed: int = 7) -> dict:
    """Historical training pipeline with time-ordered validation (no shuffle)."""

    from sklearn.metrics import accuracy_score, precision_score, recall_score

    connector = make_connector(cfg, seed=seed) if cfg.data_source == "synthetic" else make_connector(cfg)
    h1, m30, m15 = load_history(cfg, connector)
    print(f"Loaded bars -> H1={len(h1)} M30={len(m30)} M15={len(m15)}")

    X, y, ts = build_training_dataset(h1, m30, m15, cfg)
    print(f"Built dataset -> samples={len(X)} features={X.shape[1]} positive_rate={y.mean():.3f}")

    if len(X) < 500 or y.nunique() < 2:
        raise RuntimeError("Insufficient/one-class training data; increase --bars.")

    # 1) Chronological cross-validation (no shuffle).
    cv = cross_validate(X, y, cfg, n_splits)

    # 2) Chronological holdout evaluation.
    X_tr, X_te, y_tr, y_te = time_ordered_split(X, y, test_frac)
    model = MLModel(feature_names=FEATURE_COLUMNS, backends=cfg.model_backends)
    model.fit(X_tr, y_tr)
    proba_te = model.predict_success_proba(X_te)
    pred_te = (proba_te >= 0.5).astype(int)
    holdout = {
        "holdout_auc": _safe_auc(y_te, proba_te),
        "holdout_accuracy": float(accuracy_score(y_te, pred_te)),
        "holdout_precision": float(precision_score(y_te, pred_te, zero_division=0)),
        "holdout_recall": float(recall_score(y_te, pred_te, zero_division=0)),
        "holdout_samples": int(len(y_te)),
        "holdout_positive_rate": float(y_te.mean()),
    }

    # 3) Refit on ALL chronological data for the deployed model.
    final = MLModel(feature_names=FEATURE_COLUMNS, backends=cfg.model_backends)
    final.fit(X, y)
    importances = final.feature_importance()

    metadata = {
        "symbol": cfg.symbol,
        "backend": final.backend,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_samples": int(len(X)),
        "n_features": int(X.shape[1]),
        "positive_rate": float(y.mean()),
        "data_source": cfg.data_source,
        "feature_importance": importances,
        "metrics": {**cv, **holdout},
        "label": {
            "horizon": cfg.label_horizon,
            "atr_sl_mult": cfg.atr_sl_mult,
            "risk_reward": cfg.risk_reward,
        },
    }
    final.metadata = metadata

    path = final.save(cfg.model_path)
    with open(str(path) + ".meta.json", "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)

    print("\n" + "=" * 60)
    print("TRAINING REPORT")
    print("=" * 60)
    print(f"Backend            : {final.backend}")
    print(f"Samples            : {metadata['n_samples']} (pos rate {metadata['positive_rate']:.3f})")
    print(f"CV AUC (time-split): {cv['cv_auc_mean']:.3f} +/- {cv['cv_auc_std']:.3f} over {cv['cv_folds']} folds")
    print(f"CV accuracy        : {cv['cv_accuracy_mean']:.3f}")
    print(f"Holdout AUC        : {holdout['holdout_auc']:.3f}")
    print(f"Holdout accuracy   : {holdout['holdout_accuracy']:.3f}")
    print(f"Holdout precision  : {holdout['holdout_precision']:.3f}")
    print(f"Holdout recall     : {holdout['holdout_recall']:.3f}")
    print("Top features       :")
    for name, imp in list(importances.items())[:8]:
        print(f"   {name:<22} {imp:.3f}")
    print(f"Model saved to     : {path}")
    print("=" * 60)
    return metadata


# ===========================================================================
# smc_ml_brain
# ===========================================================================
@dataclass
class Decision:
    action: str  # BUY | SELL | NONE
    reason: str
    buy_prob: float
    sell_prob: float
    features = None


class SMCBrain:
    def __init__(self, cfg: Config, connector=None):
        self.cfg = cfg
        cfg.ensure_dirs()
        self.log = setup_logger(cfg)
        self.model = MLModel.load(cfg.model_path)
        self.connector = connector or make_connector(cfg)
        self.commands = CommandManager(cfg)
        self.risk = RiskManager(cfg)
        self.log.info(
            "Loaded model backend=%s features=%d min_conf=%.2f",
            self.model.backend, len(self.model.feature_names), cfg.ml_min_confidence,
        )
        top = list(self.model.feature_importance().items())[:6]
        self.log.info("Global feature importance: %s", ", ".join(f"{k}={v:.3f}" for k, v in top))

    def decide(self, h1: SMCState, m30: SMCState, m15: SMCState,
               buy_prob: float, sell_prob: float) -> Decision:
        thr = self.cfg.ml_min_confidence

        # H1 provides directional bias; M30 must not oppose it.
        bull_context = h1.bias == Bias.BULLISH and m30.trend >= 0
        bear_context = h1.bias == Bias.BEARISH and m30.trend <= 0

        # M15 must show structure supporting the direction. A standing trend is
        # itself a sequence of BOS, so trend alignment counts as structural
        # confirmation for retracement entries (plus a fresh BOS/CHoCH/MSS).
        bull_struct = (m15.bos > 0 or m15.choch > 0 or m15.mss > 0 or m15.trend > 0)
        bear_struct = (m15.bos < 0 or m15.choch < 0 or m15.mss < 0 or m15.trend < 0)

        # A valid entry area (order block or fair value gap) must exist.
        bull_area = m15.nearest_bull_ob is not None or m15.nearest_bull_fvg is not None
        bear_area = m15.nearest_bear_ob is not None or m15.nearest_bear_fvg is not None

        # Premium/discount: avoid buying at the extreme top / selling at the
        # extreme bottom. The ML model already weighs location via ``pd_dir``.
        bull_location = m15.premium_discount <= 0.85
        bear_location = m15.premium_discount >= 0.15

        buy_ok = bull_context and bull_struct and bull_area and bull_location and buy_prob >= thr
        sell_ok = bear_context and bear_struct and bear_area and bear_location and sell_prob >= thr

        if buy_ok and (not sell_ok or buy_prob >= sell_prob):
            return Decision("BUY", "all conditions met", buy_prob, sell_prob)
        if sell_ok:
            return Decision("SELL", "all conditions met", buy_prob, sell_prob)

        if not (bull_context or bear_context):
            reason = "no H1/M30 directional context"
        elif buy_prob < thr and sell_prob < thr:
            reason = f"ML below threshold (buy={buy_prob:.2f}, sell={sell_prob:.2f} < {thr:.2f})"
        elif not (bull_struct or bear_struct):
            reason = "no M15 structure (BOS/MSS/CHoCH)"
        elif not (bull_area or bear_area):
            reason = "no OB/FVG entry area"
        else:
            reason = "SMC/ML conditions not aligned"
        return Decision("NONE", reason, buy_prob, sell_prob)

    def run_cycle(self) -> Decision:
        cfg = self.cfg
        self.commands.touch_heartbeat()

        status = self.commands.read_status()
        open_positions = self.commands.open_positions(status)

        h1_df = self.connector.get_rates(cfg.bias_timeframe, cfg.live_bars)
        m30_df = self.connector.get_rates(cfg.confirm_timeframe, cfg.live_bars)
        m15_df = self.connector.get_rates(cfg.entry_timeframe, cfg.live_bars)

        h1 = analyze(h1_df, cfg.atr_period)
        m30 = analyze(m30_df, cfg.atr_period)
        m15 = analyze(m15_df, cfg.atr_period)

        _, buy_feat, sell_feat = build_live_features(h1_df, m30_df, m15_df, cfg)
        buy_prob = float(self.model.predict_success_proba(buy_feat)[0])
        sell_prob = float(self.model.predict_success_proba(sell_feat)[0])

        decision = self.decide(h1, m30, m15, buy_prob, sell_prob)

        m15_setup = self._setup_tag(m15)
        ob_present = bool(m15.nearest_bull_ob or m15.nearest_bear_ob)
        fvg_present = bool(m15.nearest_bull_fvg or m15.nearest_bear_fvg)
        self.log.info(
            format_decision_line(
                cfg.symbol, h1.bias.value, m30.bias.value, m15_setup,
                m15.bos, m15.mss, m15.choch, m15.liquidity_sweep, m15.equal_liquidity_sweep,
                ob_present, fvg_present, buy_prob, sell_prob, decision.action,
            )
        )

        if decision.action == "NONE":
            self.log.info("No trade: %s", decision.reason)
            return decision

        if not self.risk.can_open(open_positions):
            self.log.info("Skip %s: existing open position (%d)", decision.action, open_positions)
            return Decision("NONE", "existing position", buy_prob, sell_prob)

        tick = self.connector.get_tick(cfg.symbol)
        if not self.risk.check_spread(tick["spread_points"]):
            self.log.warning("Skip %s: spread %.1f > max %.1f", decision.action,
                             tick["spread_points"], cfg.max_spread_points)
            return Decision("NONE", "spread too wide", buy_prob, sell_prob)

        symbol_info = self.connector.symbol_info(cfg.symbol)
        balance = self.connector.account_info().get("balance", 0.0)
        entry = tick["ask"] if decision.action == "BUY" else tick["bid"]
        state = m15
        plan = self.risk.build_trade_plan(decision.action, entry, state, symbol_info, balance)

        problems = []
        if plan.lots <= 0:
            problems.append("lots<=0")
        if not self.risk.validate_rr(decision.action, plan.entry, plan.sl, plan.tp):
            problems.append(f"rr!=1:{cfg.risk_reward:g} (got {plan.rr:.2f})")
        if decision.action == "BUY" and not (plan.sl < plan.entry < plan.tp):
            problems.append("invalid BUY sl/tp ordering")
        if decision.action == "SELL" and not (plan.tp < plan.entry < plan.sl):
            problems.append("invalid SELL sl/tp ordering")
        if problems:
            self.log.warning("Skip %s: %s", decision.action, "; ".join(problems))
            return Decision("NONE", "; ".join(problems), buy_prob, sell_prob)

        if not self.commands.should_send(decision.action, plan.entry, plan.sl):
            self.log.info("Skip %s: duplicate setup within cooldown", decision.action)
            return Decision("NONE", "duplicate/cooldown", buy_prob, sell_prob)

        cmd = self.commands.write_trade_command(
            action=decision.action, lots=plan.lots, sl=plan.sl, tp=plan.tp, entry=plan.entry,
            breakeven_r=plan.breakeven_r, trail_start_r=plan.trail_start_r,
            trail_enabled=plan.trail_enabled,
        )
        self.commands.mark_sent(decision.action, plan.entry, plan.sl)

        chosen_feat = buy_feat if decision.action == "BUY" else sell_feat
        explain = self.model.explain(chosen_feat)
        prob = buy_prob if decision.action == "BUY" else sell_prob
        self.log.info(
            "COMMAND %s id=%s lots=%.2f entry=%.3f sl=%.3f tp=%.3f rr=%.2f prob=%.2f",
            decision.action, cmd["id"], plan.lots, plan.entry, plan.sl, plan.tp, plan.rr, prob,
        )
        self.log.info(format_explanation(explain))
        return decision

    @staticmethod
    def _setup_tag(m15: SMCState) -> str:
        if m15.mss > 0:
            return "MSS_BULLISH"
        if m15.mss < 0:
            return "MSS_BEARISH"
        if m15.choch > 0:
            return "CHOCH_BULLISH"
        if m15.choch < 0:
            return "CHOCH_BEARISH"
        if m15.bos > 0:
            return "BOS_BULLISH"
        if m15.bos < 0:
            return "BOS_BEARISH"
        return "NONE"

    def analyze_report(self) -> str:
        """Full multi-timeframe SMC readout (BOS/CHoCH/MSS, liquidity sweep,
        equal-liquidity sweep, order block, FVG) + ML probabilities."""

        cfg = self.cfg
        h1_df = self.connector.get_rates(cfg.bias_timeframe, cfg.live_bars)
        m30_df = self.connector.get_rates(cfg.confirm_timeframe, cfg.live_bars)
        m15_df = self.connector.get_rates(cfg.entry_timeframe, cfg.live_bars)

        states = {
            "H1": analyze(h1_df, cfg.atr_period),
            "M30": analyze(m30_df, cfg.atr_period),
            "M15": analyze(m15_df, cfg.atr_period),
        }
        tick = self.connector.get_tick(cfg.symbol)

        _, buy_feat, sell_feat = build_live_features(h1_df, m30_df, m15_df, cfg)
        buy_prob = float(self.model.predict_success_proba(buy_feat)[0])
        sell_prob = float(self.model.predict_success_proba(sell_feat)[0])
        decision = self.decide(states["H1"], states["M30"], states["M15"], buy_prob, sell_prob)

        report = format_smc_report(cfg.symbol, states, tick)
        report += (
            f"\nML_BUY={buy_prob:.2f}  ML_SELL={sell_prob:.2f}  "
            f"MIN_CONF={cfg.ml_min_confidence:.2f}  ->  DECISION={decision.action}"
            + ("" if decision.action != "NONE" else f"  ({decision.reason})")
        )
        for line in report.splitlines():
            self.log.info(line)
        return report

    def run_live(self, iterations: int | None = None) -> None:
        i = 0
        while iterations is None or i < iterations:
            try:
                self.run_cycle()
            except Exception as exc:  # keep the loop alive; log and continue
                self.log.exception("Cycle error: %s", exc)
            i += 1
            if iterations is None or i < iterations:
                time.sleep(self.cfg.poll_interval_sec)

    def run_replay(self, steps: int, warmup: int = 300, start_index: int | None = None) -> dict:
        """Replay the offline synthetic feed to demonstrate the full pipeline."""

        if not isinstance(self.connector, SyntheticConnector):
            raise RuntimeError("replay mode requires the synthetic connector")
        timeline = self.connector.timeline()
        if start_index is not None:
            start = max(warmup, start_index)
            window = timeline[start:start + steps]
        else:
            start = max(warmup, len(timeline) - steps)
            window = timeline[start:]
        counts = {"BUY": 0, "SELL": 0, "NONE": 0}
        for ts in window:
            self.connector.set_cutoff_time(ts)
            decision = self.run_cycle()
            counts[decision.action] = counts.get(decision.action, 0) + 1
        self.log.info("Replay finished over %d bars: %s", len(window), counts)
        return counts


# ===========================================================================
# Unified CLI
# ===========================================================================
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ml_smc_robot_all_in_one",
        description="ML + SMC trading robot (single-file). Train the model or run the brain.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # --- train ---
    tp = sub.add_parser("train", help="Train the ML model on historical data.")
    tp.add_argument("--source", choices=["mt5", "synthetic", "csv"], default="synthetic")
    tp.add_argument("--symbol", type=str, default=None, help="Override symbol (see SYMBOL_PRESETS).")
    tp.add_argument("--bars", type=int, default=None, help="Bars per timeframe to load.")
    tp.add_argument("--test-frac", type=float, default=0.2, help="Chronological holdout fraction.")
    tp.add_argument("--splits", type=int, default=4, help="TimeSeriesSplit folds.")
    tp.add_argument("--seed", type=int, default=7, help="Synthetic data seed.")
    tp.add_argument("--model-out", type=str, default=None, help="Override model output path.")

    # --- run ---
    rp = sub.add_parser("run", help="Run the SMC/ML brain (live, once, analyze or replay).")
    rp.add_argument("--source", choices=["mt5", "synthetic", "csv"], default="mt5")
    rp.add_argument("--symbol", type=str, default=None, help="Override symbol (see SYMBOL_PRESETS).")
    rp.add_argument("--once", action="store_true", help="Run a single decision cycle then exit.")
    rp.add_argument("--analyze", action="store_true", help="Print a full SMC readout then exit.")
    rp.add_argument("--iterations", type=int, default=None, help="Number of live cycles then exit.")
    rp.add_argument("--replay", type=int, default=None, help="Replay N synthetic bars (offline demo).")
    rp.add_argument("--replay-start", type=int, default=None, help="Start index for replay window.")
    rp.add_argument("--seed", type=int, default=7, help="Synthetic data seed.")
    rp.add_argument("--balance", type=float, default=1000.0, help="Synthetic account balance.")
    rp.add_argument("--min-confidence", type=float, default=None, help="Override ML_MIN_CONFIDENCE.")
    rp.add_argument("--bridge-dir", type=str, default=None, help="Override bridge directory.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "train":
        overrides = {"data_source": args.source}
        if args.symbol:
            overrides["symbol"] = args.symbol
        cfg = Config.from_env(**overrides)
        if args.bars:
            cfg.train_bars = args.bars
        if args.model_out:
            cfg.model_dir = Path(args.model_out).parent
            cfg.model_filename = Path(args.model_out).name
        cfg.ensure_dirs()
        train(cfg, test_frac=args.test_frac, n_splits=args.splits, seed=args.seed)
        return 0

    # args.command == "run"
    overrides = {"data_source": args.source}
    if args.symbol:
        overrides["symbol"] = args.symbol
    cfg = Config.from_env(**overrides)
    if args.min_confidence is not None:
        cfg.ml_min_confidence = args.min_confidence
    if args.bridge_dir:
        cfg.bridge_dir = Path(args.bridge_dir)
    cfg.ensure_dirs()

    connector = None
    if cfg.data_source == "synthetic":
        connector = SyntheticConnector(cfg, seed=args.seed, balance=args.balance)

    brain = SMCBrain(cfg, connector=connector)

    if args.analyze:
        print(brain.analyze_report())
    elif args.replay is not None:
        brain.run_replay(args.replay, start_index=args.replay_start)
    elif args.once:
        brain.run_cycle()
    else:
        brain.run_live(iterations=args.iterations)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
