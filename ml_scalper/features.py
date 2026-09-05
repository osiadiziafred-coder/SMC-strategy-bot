"""Causal feature engineering for the ML scalper.

Timeframe roles (no SMC):

* M15 — market / trend regime (EMA 20/50, VWAP, RSI, trend strength)
* M5  — primary scalping setup (pullback, distance to EMA/VWAP, momentum, candles)
* M1  — optional precision context; never the sole signal (critical for V50 1s)

A direction feature (+1 BUY / -1 SELL) plus interaction terms lets one outcome
model score both sides of a setup. Labels are triple-barrier: 1 if TP is hit
before SL inside the horizon at the configured 1:2 RR.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind
from .config import Config

BASE_FEATURES: list[str] = [
    "m15_ema20_dist",
    "m15_ema50_dist",
    "m15_ema_spread",
    "m15_trend",
    "m15_trend_strength",
    "m15_rsi",
    "m15_atr_pct",
    "m15_ret_1",
    "m15_ret_3",
    "m15_vwap_dist",
    "m5_ema20_dist",
    "m5_ema50_dist",
    "m5_vwap_dist",
    "m5_rsi",
    "m5_rsi_slope",
    "m5_momentum",
    "m5_momentum_slope",
    "m5_atr_pct",
    "m5_atr_ratio",
    "m5_body",
    "m5_upper_wick",
    "m5_lower_wick",
    "m5_range",
    "m5_body_ratio",
    "m5_ret_1",
    "m5_ret_3",
    "m5_ret_5",
    "m5_ret_10",
    "m5_volume_rel",
    "m5_spread",
    "m5_spread_rel",
    "m5_trend_strength",
    "m5_pullback_depth",
    "m5_near_ma",
    "mtf_trend_align",
    "m1_ema20_dist",
    "m1_rsi",
    "m1_momentum",
    "m1_body",
    "m1_ret_1",
    "m1_ret_3",
    "hour_sin",
    "hour_cos",
]

DIRECTION_FEATURES: list[str] = [
    "direction",
    "regime_align",
    "ema_dist_dir",
    "vwap_dist_dir",
    "momentum_dir",
    "rsi_dir",
    "pullback_dir",
    "wick_dir",
]

FEATURE_COLUMNS: list[str] = BASE_FEATURES + DIRECTION_FEATURES

CLASS_NONE = 0
CLASS_BUY = 1
CLASS_SELL = 2
CLASS_NAMES = {CLASS_NONE: "NO_TRADE", CLASS_BUY: "BUY", CLASS_SELL: "SELL"}


def _sanitize(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)


def _vwap(df: pd.DataFrame, cfg: Config) -> pd.Series:
    if cfg.session_vwap:
        return ind.session_vwap(df)
    return ind.rolling_vwap(df, cfg.vwap_window)


def _tf_block(df: pd.DataFrame, cfg: Config, prefix: str) -> pd.DataFrame:
    close = df["close"]
    ema20 = ind.ema(close, cfg.ema_fast)
    ema50 = ind.ema(close, cfg.ema_slow)
    atr_s = ind.atr(df, cfg.atr_period)
    atr_safe = atr_s.replace(0.0, np.nan)
    vwap = _vwap(df, cfg)
    rsi_s = ind.rsi(close, cfg.rsi_period)
    parts = ind.candle_parts(df)
    out = pd.DataFrame(index=df.index)
    out[f"{prefix}_ema20_dist"] = ind.distance_atr(close, ema20, atr_s)
    out[f"{prefix}_ema50_dist"] = ind.distance_atr(close, ema50, atr_s)
    out[f"{prefix}_ema_spread"] = (ema20 - ema50) / atr_safe
    out[f"{prefix}_trend"] = ind.trend_sign(ema20, ema50)
    out[f"{prefix}_trend_strength"] = ind.trend_strength(ema20, ema50, atr_s)
    out[f"{prefix}_rsi"] = rsi_s
    out[f"{prefix}_atr_pct"] = atr_s / close.replace(0.0, np.nan)
    out[f"{prefix}_vwap_dist"] = ind.distance_atr(close, vwap, atr_s)
    out[f"{prefix}_ret_1"] = ind.log_return(close, 1)
    out[f"{prefix}_ret_3"] = ind.log_return(close, 3)
    out[f"{prefix}_momentum"] = ind.momentum(close, 3) / atr_safe
    out[f"{prefix}_body"] = parts["body"] / atr_safe
    out[f"{prefix}_upper_wick"] = parts["upper_wick"] / atr_safe
    out[f"{prefix}_lower_wick"] = parts["lower_wick"] / atr_safe
    out[f"{prefix}_range"] = parts["range"] / atr_safe
    out[f"{prefix}_body_ratio"] = parts["body_ratio"]
    return out


def compute_setup_extras(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    close = df["close"]
    atr_s = ind.atr(df, cfg.atr_period)
    atr_safe = atr_s.replace(0.0, np.nan)
    rsi_s = ind.rsi(close, cfg.rsi_period)
    mom = ind.momentum(close, 3) / atr_safe
    ema20 = ind.ema(close, cfg.ema_fast)
    vwap = _vwap(df, cfg)
    near_ema = (close - ema20).abs() / atr_safe
    near_vwap = (close - vwap).abs() / atr_safe
    spread = df["spread"] if "spread" in df.columns else pd.Series(0.0, index=df.index)
    spread_med = spread.rolling(50, min_periods=10).median().replace(0.0, np.nan)
    atr_med = atr_s.rolling(100, min_periods=20).median().replace(0.0, np.nan)

    out = pd.DataFrame(index=df.index)
    out["m5_rsi_slope"] = rsi_s.diff(2)
    out["m5_momentum_slope"] = mom.diff(1)
    out["m5_ret_5"] = ind.log_return(close, 5)
    out["m5_ret_10"] = ind.log_return(close, 10)
    out["m5_volume_rel"] = ind.volume_relative(df)
    out["m5_spread"] = spread
    out["m5_spread_rel"] = spread / spread_med
    out["m5_atr_ratio"] = atr_s / atr_med
    out["m5_pullback_depth"] = ind.pullback_depth(df["high"], df["low"], close, atr_s)
    out["m5_near_ma"] = pd.concat([near_ema, near_vwap], axis=1).min(axis=1)
    hour_sin, hour_cos = ind.hour_cycle(df.index)
    out["hour_sin"] = hour_sin
    out["hour_cos"] = hour_cos
    return out


def _asof_prefix(left: pd.DataFrame, right: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if right.empty:
        extra = pd.DataFrame(0.0, index=left.index, columns=columns)
        return pd.concat([left, extra], axis=1)
    src = right[columns].sort_index()
    merged = pd.merge_asof(
        left.sort_index(),
        src,
        left_index=True,
        right_index=True,
        direction="backward",
    )
    return merged


def build_base_matrix(
    m15: pd.DataFrame,
    m5: pd.DataFrame,
    m1: pd.DataFrame | None,
    cfg: Config,
) -> pd.DataFrame:
    """Direction-independent features aligned to M5 bars."""

    setup = _tf_block(m5, cfg, "m5")
    extras = compute_setup_extras(m5, cfg)
    setup = pd.concat([setup, extras], axis=1)

    regime = _tf_block(m15, cfg, "m15")
    regime_cols = [
        "m15_ema20_dist",
        "m15_ema50_dist",
        "m15_ema_spread",
        "m15_trend",
        "m15_trend_strength",
        "m15_rsi",
        "m15_atr_pct",
        "m15_ret_1",
        "m15_ret_3",
        "m15_vwap_dist",
    ]
    setup = _asof_prefix(setup, regime, regime_cols)

    m1_cols = ["m1_ema20_dist", "m1_rsi", "m1_momentum", "m1_body", "m1_ret_1", "m1_ret_3"]
    if m1 is not None and len(m1) > 0 and cfg.use_m1_precision:
        micro = _tf_block(m1, cfg, "m1")
        keep = [c for c in m1_cols if c in micro.columns]
        setup = _asof_prefix(setup, micro, keep)
        for c in m1_cols:
            if c not in setup.columns:
                setup[c] = 0.0
    else:
        for c in m1_cols:
            setup[c] = 0.0

    setup["mtf_trend_align"] = np.sign(setup["m15_trend"]) + np.sign(setup["m5_trend"])
    missing = [c for c in BASE_FEATURES if c not in setup.columns]
    for c in missing:
        setup[c] = 0.0
    return _sanitize(setup[BASE_FEATURES])


def add_direction_features(base: pd.DataFrame, direction: int) -> pd.DataFrame:
    if direction not in (1, -1):
        raise ValueError("direction must be +1 (BUY) or -1 (SELL)")
    out = base.copy()
    out["direction"] = float(direction)
    out["regime_align"] = out["m15_trend"] * direction
    out["ema_dist_dir"] = out["m5_ema20_dist"] * direction
    out["vwap_dist_dir"] = out["m5_vwap_dist"] * direction
    out["momentum_dir"] = out["m5_momentum"] * direction
    out["rsi_dir"] = (out["m5_rsi"] - 50.0) * direction
    out["pullback_dir"] = out["m5_pullback_depth"] * direction
    # Lower wick supports BUY; upper wick supports SELL.
    out["wick_dir"] = np.where(direction > 0, out["m5_lower_wick"], out["m5_upper_wick"])
    return _sanitize(out[FEATURE_COLUMNS])


def triple_barrier_labels(
    df: pd.DataFrame,
    atr_s: pd.Series,
    direction: int,
    horizon: int,
    atr_sl_mult: float,
    risk_reward: float,
) -> pd.Series:
    """1 if TP is hit before SL within ``horizon`` bars, else 0. NaN at the tail."""

    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    atr_v = atr_s.to_numpy()
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


def setup_masks(base: pd.DataFrame, cfg: Config) -> tuple[pd.Series, pd.Series]:
    """Loose training masks: regime aligned, not extended, near a moving average."""

    near = base["m5_near_ma"] <= max(cfg.near_ma_atr, 1.5)
    strength = base["m15_trend_strength"] >= min(cfg.min_trend_strength, 0.08)
    bull = (base["m15_trend"] > 0) & (base["m5_ema50_dist"] > -0.5) & near & strength
    bear = (base["m15_trend"] < 0) & (base["m5_ema50_dist"] < 0.5) & near & strength
    return bull.fillna(False), bear.fillna(False)


def live_setup_flags(base_row: pd.Series, cfg: Config) -> dict[str, bool]:
    """Strict live filters matching the BUY/SELL models in the spec."""

    m15_bull = float(base_row["m15_trend"]) > 0 and float(base_row["m15_trend_strength"]) >= cfg.min_trend_strength
    m15_bear = float(base_row["m15_trend"]) < 0 and float(base_row["m15_trend_strength"]) >= cfg.min_trend_strength
    near = float(base_row["m5_near_ma"]) <= cfg.near_ma_atr
    depth = float(base_row["m5_pullback_depth"])
    pullback_buy = cfg.pullback_atr_min <= depth <= cfg.pullback_atr_max
    pullback_sell = cfg.pullback_atr_min <= -depth <= cfg.pullback_atr_max
    mom_up = float(base_row["m5_momentum_slope"]) > 0 or float(base_row["m5_rsi_slope"]) > 0
    mom_down = float(base_row["m5_momentum_slope"]) < 0 or float(base_row["m5_rsi_slope"]) < 0
    m1_buy = True
    m1_sell = True
    if cfg.require_m1_confirm:
        m1_buy = float(base_row["m1_momentum"]) > 0 or float(base_row["m1_body"]) > 0
        m1_sell = float(base_row["m1_momentum"]) < 0 or float(base_row["m1_body"]) < 0
    buy_ok = m15_bull and pullback_buy and near and mom_up and m1_buy
    sell_ok = m15_bear and pullback_sell and near and mom_down and m1_sell
    return {
        "m15_bull": m15_bull,
        "m15_bear": m15_bear,
        "near_ma": near,
        "pullback_buy": pullback_buy,
        "pullback_sell": pullback_sell,
        "momentum_up": mom_up,
        "momentum_down": mom_down,
        "buy_setup": buy_ok,
        "sell_setup": sell_ok,
    }


def abnormal_conditions(base_row: pd.Series, spread_points: float, cfg: Config) -> str | None:
    atr_ratio = float(base_row.get("m5_atr_ratio", 1.0))
    if np.isfinite(atr_ratio) and atr_ratio >= cfg.abnormal_atr_mult:
        return f"abnormal volatility (atr_ratio={atr_ratio:.2f})"
    spread_rel = float(base_row.get("m5_spread_rel", 1.0))
    if np.isfinite(spread_rel) and spread_rel >= cfg.max_spread_vs_median:
        return f"abnormal spread vs median ({spread_rel:.2f}x)"
    if spread_points > cfg.max_spread_points:
        return f"spread {spread_points:.1f} > max {cfg.max_spread_points:.1f}"
    return None


def build_training_dataset(
    m15: pd.DataFrame,
    m5: pd.DataFrame,
    m1: pd.DataFrame | None,
    cfg: Config,
) -> dict:
    """Return matrices for the 3-class direction model and the binary outcome model."""

    base = build_base_matrix(m15, m5, m1, cfg)
    atr_s = ind.atr(m5, cfg.atr_period)
    y_buy = triple_barrier_labels(m5, atr_s, 1, cfg.label_horizon, cfg.atr_sl_mult, cfg.risk_reward)
    y_sell = triple_barrier_labels(m5, atr_s, -1, cfg.label_horizon, cfg.atr_sl_mult, cfg.risk_reward)
    bull_mask, bear_mask = setup_masks(base, cfg)

    # --- 3-class direction / selection labels --------------------------------
    y_dir = np.full(len(base), np.nan)
    buy_win = (y_buy == 1) & bull_mask
    sell_win = (y_sell == 1) & bear_mask
    both = buy_win & sell_win
    y_dir[buy_win.to_numpy() & ~both.to_numpy()] = CLASS_BUY
    y_dir[sell_win.to_numpy() & ~both.to_numpy()] = CLASS_SELL
    # If both sides would have won, pick the side with stronger regime alignment.
    if both.any():
        pick_buy = base.loc[both, "m15_trend"] >= 0
        y_dir[both.to_numpy()] = np.where(pick_buy.to_numpy(), CLASS_BUY, CLASS_SELL)
    labeled = y_buy.notna() & y_sell.notna()
    none_idx = labeled.to_numpy() & np.isnan(y_dir)
    y_dir[none_idx] = CLASS_NONE
    dir_valid = np.isfinite(y_dir)
    X_dir = base.loc[dir_valid].reset_index(drop=True)
    y_dir_s = pd.Series(y_dir[dir_valid], dtype=int).reset_index(drop=True)
    ts_dir = pd.Series(base.index[dir_valid]).reset_index(drop=True)

    # --- Binary outcome labels (direction-conditioned) -----------------------
    frames_X, frames_y, times = [], [], []
    for direction, y_side in ((1, y_buy), (-1, y_sell)):
        X_d = add_direction_features(base, direction)
        valid = y_side.notna()
        frames_X.append(X_d.loc[valid])
        frames_y.append(y_side.loc[valid].astype(int))
        times.append(pd.Series(X_d.index[valid], index=X_d.index[valid]))
    X_out = pd.concat(frames_X)
    y_out = pd.concat(frames_y)
    ts_out = pd.concat(times)
    order = np.argsort(ts_out.to_numpy(), kind="stable")
    X_out = X_out.iloc[order].reset_index(drop=True)
    y_out = y_out.iloc[order].reset_index(drop=True)
    ts_out = ts_out.iloc[order].reset_index(drop=True)

    return {
        "X_dir": X_dir,
        "y_dir": y_dir_s,
        "ts_dir": ts_dir,
        "X_out": X_out,
        "y_out": y_out,
        "ts_out": ts_out,
        "base": base,
    }


def build_live_features(
    m15: pd.DataFrame,
    m5: pd.DataFrame,
    m1: pd.DataFrame | None,
    cfg: Config,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = build_base_matrix(m15, m5, m1, cfg)
    last = base.iloc[[-1]]
    return last, add_direction_features(last, 1), add_direction_features(last, -1)
