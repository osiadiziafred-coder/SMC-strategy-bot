"""Feature engineering for the ML/SMC brain.

The same vectorised, *causal* functions are used for both training (thousands of
historical bars) and live inference (the latest bar), which guarantees the model
sees identically-constructed features in production and during training.

The feature matrix combines the three timeframes:

* H1 - major bias/trend context
* M30 - confirmation context
* M15 - the entry timeframe (full SMC feature set)

A ``direction`` feature (+1 BUY / -1 SELL) plus a handful of direction-interaction
features let a single model output the probability of success for a BUY *and* a
SELL from the same market state.

All outputs are sanitised: infinities and NaNs are removed so downstream models
never receive invalid values.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import smc_detector as smc
from .config import Config

# Direction-independent features describing the market state.
BASE_FEATURES: list[str] = [
    "h1_trend",
    "m30_trend",
    "m15_trend",
    "m15_bos",
    "m15_mss",
    "m15_choch",
    "m15_sweep",
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

# Direction-dependent features (built once the trade direction is hypothesised).
DIRECTION_FEATURES: list[str] = [
    "direction",
    "trend_dir_align",
    "struct_dir_align",
    "pd_dir",
    "momentum_dir",
    "sweep_dir",
]

FEATURE_COLUMNS: list[str] = BASE_FEATURES + DIRECTION_FEATURES


def _sanitize(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.replace([np.inf, -np.inf], np.nan)
        .ffill()
        .fillna(0.0)
    )


def compute_context_features(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Trend/structure context for a higher timeframe (H1/M30)."""

    out = pd.DataFrame(index=df.index)
    out[f"{prefix}_trend"] = smc.trend_series(df)
    out[f"{prefix}_bos"] = smc.bos_series(df)
    out[f"{prefix}_choch"] = smc.choch_series(df)
    out[f"{prefix}_premium_discount"] = smc.premium_discount_series(df)
    return out


def compute_entry_features(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Full SMC feature set for the entry (M15) timeframe, ATR-normalised."""

    atr = smc.atr_series(df, cfg.atr_period)
    atr_safe = atr.replace(0, np.nan)
    close = df["close"]

    swing_high = smc.rolling_swing_high(df)
    swing_low = smc.rolling_swing_low(df)

    out = pd.DataFrame(index=df.index)
    out["m15_trend"] = smc.trend_series(df)
    out["m15_bos"] = smc.bos_series(df)
    out["m15_mss"] = smc.mss_series(df)
    out["m15_choch"] = smc.choch_series(df)
    out["m15_sweep"] = smc.liquidity_sweep_series(df)
    out["m15_ob_distance"] = smc.order_block_distance_series(df) / atr_safe
    fvg_bull = smc.fvg_bullish_size(df)
    fvg_bear = smc.fvg_bearish_size(df)
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
    out["m15_momentum"] = smc.momentum_series(df) / atr_safe
    out["m15_volatility"] = smc.volatility_series(df)
    out["m15_premium_discount"] = smc.premium_discount_series(df)
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
    ``horizon`` bars, else 0. Uses only *future* bars for the label (this is
    correct supervised labelling) while features remain causal."""

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
    atr = smc.atr_series(m15, cfg.atr_period)

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
