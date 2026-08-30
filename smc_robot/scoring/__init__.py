"""Feature extraction, hybrid rule + ML scoring, and setup grading."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from smc_robot.config import Settings
from smc_robot.models import (
    Direction,
    EventType,
    LiquiditySweep,
    MarketConditions,
    ScoreBreakdown,
    SetupGrade,
    Trend,
    Zone,
)
from smc_robot.smc.analyze import TimeframeAnalysis
from smc_robot.smc.fvg import interacting_fvgs
from smc_robot.smc.liquidity import recent_sweeps
from smc_robot.smc.order_blocks import interacting_blocks
from smc_robot.smc.indicators import atr
from smc_robot.smc.premium_discount import structure_premium_discount
from smc_robot.smc.structure import recent_events

FEATURE_NAMES = [
    "h1_trend",
    "m30_trend",
    "m15_trend",
    "h1_aligned",
    "h1_conflict",
    "m30_bos",
    "m30_choch",
    "m30_mss",
    "m15_bos",
    "m15_choch",
    "m15_mss",
    "sweep",
    "sweep_equal",
    "sweep_external",
    "sweep_rejection",
    "ob_interact",
    "fvg_interact",
    "atr_ratio",
    "efficiency",
    "spread_ratio",
    "poor_conditions",
    "bars_since_sweep",
    "premium_discount",
    "displacement",
    "session_london_ny",
    "dist_liquidity",
    "dist_ob",
    "dist_fvg",
    "candle_body_atr",
    "momentum",
    "fvg_size",
    "volatility",
    "hour_utc",
    "dist_recent_high",
    "dist_recent_low",
    "reward_ratio",
    "candle_range_atr",
    "volume_ratio",
    "tick_volume",
    "spread_points",
    "atr_abs",
    "mtf_aligned",
]


def _trend_value(trend: Trend, direction: Direction) -> float:
    if trend == Trend.RANGING:
        return 0.0
    if direction == Direction.BUY:
        return 1.0 if trend == Trend.BULLISH else -1.0
    return 1.0 if trend == Trend.BEARISH else -1.0


def _has_event(events, event_type: EventType) -> float:
    return 1.0 if any(e.event_type == event_type for e in events) else 0.0


def extract_features(
    direction: Direction,
    h1: TimeframeAnalysis,
    m30: TimeframeAnalysis,
    m15: TimeframeAnalysis,
    conditions: MarketConditions,
    settings: Settings,
    sweep: Optional[LiquiditySweep],
    order_block: Optional[Zone],
    fvg: Optional[Zone],
) -> dict[str, float]:
    last = len(m15.candles) - 1
    m30_last = len(m30.candles) - 1
    m30_events = recent_events(
        m30.events, m30_last, settings.smc.structure_event_max_age_m30, direction
    )
    m15_events = recent_events(
        m15.events, last, settings.smc.structure_event_max_age_m15, direction
    )
    h1_value = _trend_value(h1.trend, direction)
    pd = structure_premium_discount(
        m15.candles,
        h1.external_swings or m15.external_swings,
        direction,
        settings.smc.discount_max,
        settings.smc.premium_min,
    )
    conditions.premium_discount = pd
    session = conditions.session.value
    last_c = m15.candles[-1]
    atr_v = conditions.atr or atr(m15.candles, settings.smc.atr_period)
    price = last_c.close
    liq_price = sweep.swept_price if sweep is not None else None
    ob_mid = order_block.mid if order_block is not None else None
    fvg_mid = fvg.mid if fvg is not None else None
    body_atr = (last_c.body / atr_v) if atr_v > 0 else 0.0
    look = m15.candles[-6] if len(m15.candles) >= 6 else m15.candles[0]
    momentum = ((price - look.close) / atr_v) if atr_v > 0 else 0.0
    recent = m15.candles[-20:] if len(m15.candles) >= 20 else m15.candles
    recent_high = max(c.high for c in recent)
    recent_low = min(c.low for c in recent)
    fvg_size = 0.0
    if fvg is not None and atr_v > 0:
        fvg_size = (fvg.high - fvg.low) / atr_v
    hour = last_c.time.hour + last_c.time.minute / 60.0
    vols = [c.volume for c in recent if c.volume > 0]
    vol_med = float(np.median(vols)) if vols else 1.0
    range_atr = (last_c.range / atr_v) if atr_v > 0 else 0.0
    mtf = 1.0 if (
        _trend_value(h1.trend, direction) > 0
        and _trend_value(m30.trend, direction) > 0
        and _trend_value(m15.trend, direction) > 0
    ) else 0.0
    raw = {
        "h1_trend": h1_value,
        "m30_trend": _trend_value(m30.trend, direction),
        "m15_trend": _trend_value(m15.trend, direction),
        "h1_aligned": 1.0 if h1_value > 0 else 0.0,
        "h1_conflict": 1.0 if h1_value < 0 else 0.0,
        "m30_bos": _has_event(m30_events, EventType.BOS),
        "m30_choch": _has_event(m30_events, EventType.CHOCH),
        "m30_mss": _has_event(m30_events, EventType.MSS),
        "m15_bos": _has_event(m15_events, EventType.BOS),
        "m15_choch": _has_event(m15_events, EventType.CHOCH),
        "m15_mss": _has_event(m15_events, EventType.MSS),
        "sweep": 1.0 if sweep is not None else 0.0,
        "sweep_equal": 1.0 if sweep is not None and sweep.equal_liquidity else 0.0,
        "sweep_external": 1.0 if sweep is not None and sweep.pool_scope == "external" else 0.0,
        "sweep_rejection": float(sweep.rejection_ratio) if sweep is not None else 0.0,
        "ob_interact": 1.0 if order_block is not None else 0.0,
        "fvg_interact": 1.0 if fvg is not None else 0.0,
        "atr_ratio": conditions.atr_ratio,
        "efficiency": conditions.efficiency,
        "spread_ratio": conditions.spread_ratio,
        "poor_conditions": 1.0 if conditions.poor else 0.0,
        "bars_since_sweep": float(last - sweep.index) if sweep is not None else 99.0,
        "premium_discount": 1.0 if (pd.in_discount or pd.in_premium) else 0.0,
        "displacement": 1.0 if conditions.displacement.strong else 0.0,
        "session_london_ny": 1.0 if session in ("LONDON", "NEW_YORK", "LONDON_NY_OVERLAP") else 0.0,
        "dist_liquidity": _atr_dist(price, liq_price, atr_v),
        "dist_ob": _atr_dist(price, ob_mid, atr_v),
        "dist_fvg": _atr_dist(price, fvg_mid, atr_v),
        "candle_body_atr": body_atr,
        "momentum": momentum,
        "fvg_size": fvg_size,
        "volatility": conditions.atr_ratio,
        "hour_utc": hour / 23.0,
        "dist_recent_high": _atr_dist(price, recent_high, atr_v),
        "dist_recent_low": _atr_dist(price, recent_low, atr_v),
        "reward_ratio": settings.risk.reward_ratio,
        "candle_range_atr": range_atr,
        "volume_ratio": (last_c.volume / vol_med) if vol_med > 0 else 0.0,
        "tick_volume": last_c.volume,
        "spread_points": conditions.spread,
        "atr_abs": atr_v,
        "mtf_aligned": mtf,
    }
    return sanitize_features(raw)


def _atr_dist(price: float, ref: float | None, atr_v: float) -> float:
    if ref is None or atr_v <= 0:
        return 9.0
    return abs(price - ref) / atr_v


def sanitize_features(features: dict[str, float]) -> dict[str, float]:
    clean: dict[str, float] = {}
    for name in FEATURE_NAMES:
        value = features.get(name, 0.0)
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        if not np.isfinite(number):
            number = 0.0
        clean[name] = number
    return clean


def feature_vector(features: dict[str, float]) -> np.ndarray:
    safe = sanitize_features(features)
    return np.array([safe[name] for name in FEATURE_NAMES], dtype=float)


def explain_prediction(
    features: dict[str, float],
    importances: dict[str, float] | None,
    limit: int = 6,
) -> list[dict[str, float | str]]:
    if not importances:
        ranked = sorted(
            ((name, abs(float(features.get(name, 0.0)))) for name in FEATURE_NAMES),
            key=lambda item: item[1],
            reverse=True,
        )
    else:
        ranked = sorted(
            (
                (name, float(importances.get(name, 0.0)) * (1.0 + abs(float(features.get(name, 0.0)))))
                for name in FEATURE_NAMES
            ),
            key=lambda item: item[1],
            reverse=True,
        )
    return [{"feature": name, "weight": round(weight, 6)} for name, weight in ranked[:limit] if weight]


def rule_score(features: dict[str, float], settings: Settings) -> tuple[float, dict[str, float]]:
    w = settings.scoring.weights
    components: dict[str, float] = {}
    if features.get("h1_aligned", 0) > 0:
        components["h1_aligned"] = w.h1_aligned
    if features.get("h1_conflict", 0) > 0:
        components["h1_conflict"] = w.h1_conflict
    if (
        features.get("m30_bos")
        or features.get("m30_mss")
        or features.get("m30_choch")
        or features.get("m30_trend", 0) > 0
    ):
        components["m30_confirmation"] = w.m30_confirmation
    if features.get("sweep", 0) > 0:
        components["liquidity_sweep"] = w.liquidity_sweep
        extra = 0.0
        if features.get("sweep_equal", 0) > 0:
            extra += w.equal_liquidity_extra
        if features.get("sweep_external", 0) > 0:
            extra += 2.0
        if extra:
            components["liquidity_sweep"] += extra
    if features.get("ob_interact", 0) > 0:
        components["order_block"] = w.order_block
    if features.get("fvg_interact", 0) > 0:
        components["fvg"] = w.fvg
    if features.get("m15_bos", 0) > 0:
        components["bos"] = w.bos
    if features.get("m15_choch", 0) > 0:
        components["choch"] = w.choch
    if features.get("m15_mss", 0) > 0:
        components["mss"] = w.mss
    if features.get("poor_conditions", 0) > 0:
        components["poor_conditions"] = w.poor_conditions
    elif features.get("efficiency", 0) >= 0.30 and 0.8 <= features.get("atr_ratio", 1.0) <= 1.8:
        components["good_conditions"] = w.good_conditions
    if features.get("premium_discount", 0) > 0:
        components["premium_discount"] = w.premium_discount
    if features.get("displacement", 0) > 0:
        components["displacement"] = w.displacement
    total = float(sum(components.values()))
    return total, components


def grade_setup(features: dict[str, float], ml_probability: float | None, rule_total: float) -> SetupGrade:
    smc_core = (
        features.get("h1_aligned", 0) > 0
        and features.get("sweep", 0) > 0
        and (features.get("ob_interact", 0) > 0 or features.get("fvg_interact", 0) > 0)
        and (
            features.get("m15_bos", 0) > 0
            or features.get("m15_mss", 0) > 0
            or features.get("m15_choch", 0) > 0
        )
    )
    strong_structure = features.get("m15_mss", 0) > 0 or features.get("m15_bos", 0) > 0
    clean = features.get("poor_conditions", 0) <= 0
    high_ml = ml_probability is not None and ml_probability >= 0.70
    good_ml = ml_probability is not None and ml_probability >= 0.60
    if smc_core and strong_structure and clean and (high_ml or (ml_probability is None and rule_total >= 85)):
        return SetupGrade.A_PLUS
    if smc_core and (good_ml or (ml_probability is None and rule_total >= 70)):
        return SetupGrade.A
    if smc_core:
        return SetupGrade.B
    return SetupGrade.C


class SetupScorer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self.importances: dict[str, float] = {}
        if settings.scoring.use_ml:
            self._model = self._load_model(settings.scoring.model_path)

    def _load_model(self, path: str):
        model_path = Path(path)
        if not model_path.exists():
            return None
        try:
            import joblib

            payload = joblib.load(model_path)
            if isinstance(payload, dict) and "model" in payload:
                raw_imp = payload.get("feature_importance") or {}
                self.importances = {str(k): float(v) for k, v in raw_imp.items()}
                return payload["model"]
            return payload
        except Exception:
            return None

    def predict_success(self, features: dict[str, float]) -> float | None:
        if self._model is None:
            return None
        vector = feature_vector(features).reshape(1, -1)
        try:
            proba = self._model.predict_proba(vector)[0]
            if len(proba) < 2:
                return None
            return float(proba[1])
        except Exception:
            return None

    def score(
        self,
        direction: Direction,
        h1: TimeframeAnalysis,
        m30: TimeframeAnalysis,
        m15: TimeframeAnalysis,
        conditions: MarketConditions,
        sweep: Optional[LiquiditySweep],
        order_block: Optional[Zone],
        fvg: Optional[Zone],
        opposite_probability: float | None = None,
    ) -> ScoreBreakdown:
        features = extract_features(
            direction, h1, m30, m15, conditions, self.settings, sweep, order_block, fvg
        )
        rules, components = rule_score(features, self.settings)
        ml_score: Optional[float] = None
        ml_probability = self.predict_success(features)
        total = rules
        if ml_probability is not None:
            ml_score = ml_probability * 100.0
            blend = self.settings.scoring.ml_blend
            total = (1.0 - blend) * rules + blend * ml_score
        buy_p = ml_probability if direction == Direction.BUY else opposite_probability
        sell_p = ml_probability if direction == Direction.SELL else opposite_probability
        grade = grade_setup(features, ml_probability, rules)
        return ScoreBreakdown(
            total=total,
            rule_score=rules,
            ml_score=ml_score,
            ml_probability=ml_probability,
            ml_buy_probability=buy_p,
            ml_sell_probability=sell_p,
            grade=grade,
            components=components,
            features=features,
            explanation=explain_prediction(features, self.importances),
        )


def find_setup_parts(
    direction: Direction,
    m30: TimeframeAnalysis,
    m15: TimeframeAnalysis,
    settings: Settings,
) -> tuple[Optional[LiquiditySweep], Optional[Zone], Optional[Zone], list[object]]:
    last = len(m15.candles) - 1
    m30_last = len(m30.candles) - 1
    sweeps = recent_sweeps(m15.sweeps, last, settings.smc.sweep_lookback_bars, direction)
    if not sweeps:
        sweeps = recent_sweeps(m30.sweeps, m30_last, max(3, settings.smc.sweep_lookback_bars // 2), direction)
    sweep = None
    if sweeps:
        sweeps = sorted(
            sweeps,
            key=lambda s: (s.equal_liquidity, s.pool_scope == "external", s.rejection_ratio, s.index),
        )
        sweep = sweeps[-1]
    obs = interacting_blocks(m15.candles, m15.order_blocks, direction, settings.smc.ob_max_age_bars)
    if not obs:
        obs = interacting_blocks(m30.candles, m30.order_blocks, direction, settings.smc.ob_max_age_bars)
    fvgs = interacting_fvgs(m15.candles, m15.fvgs, direction)
    if not fvgs:
        fvgs = interacting_fvgs(m30.candles, m30.fvgs, direction)
    m30_events = recent_events(
        m30.events, m30_last, settings.smc.structure_event_max_age_m30, direction
    )
    return sweep, (obs[-1] if obs else None), (fvgs[-1] if fvgs else None), m30_events


def nearest_opposing_liquidity(
    analysis: TimeframeAnalysis,
    direction: Direction,
    entry: float,
) -> float | None:
    prices: list[float] = []
    for pool in analysis.pools:
        if direction == Direction.BUY and pool.kind.value == "HIGH" and pool.price > entry:
            prices.append(pool.price)
        if direction == Direction.SELL and pool.kind.value == "LOW" and pool.price < entry:
            prices.append(pool.price)
    if not prices:
        return None
    return min(prices, key=lambda p: abs(p - entry))
