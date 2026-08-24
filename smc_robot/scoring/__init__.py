"""Feature extraction and hybrid rule + ML setup scoring."""

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
    Trend,
    Zone,
)
from smc_robot.smc.analyze import TimeframeAnalysis
from smc_robot.smc.structure import recent_events
from smc_robot.smc.liquidity import recent_sweeps
from smc_robot.smc.order_blocks import interacting_blocks
from smc_robot.smc.fvg import interacting_fvgs

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
    "ob_interact",
    "fvg_interact",
    "atr_ratio",
    "efficiency",
    "spread_ratio",
    "poor_conditions",
    "bars_since_sweep",
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
    return {
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
        "ob_interact": 1.0 if order_block is not None else 0.0,
        "fvg_interact": 1.0 if fvg is not None else 0.0,
        "atr_ratio": conditions.atr_ratio,
        "efficiency": conditions.efficiency,
        "spread_ratio": conditions.spread_ratio,
        "poor_conditions": 1.0 if conditions.poor else 0.0,
        "bars_since_sweep": float(last - sweep.index) if sweep is not None else 99.0,
    }


def feature_vector(features: dict[str, float]) -> np.ndarray:
    return np.array([features[name] for name in FEATURE_NAMES], dtype=float)


def rule_score(features: dict[str, float], settings: Settings) -> tuple[float, dict[str, float]]:
    w = settings.scoring.weights
    components: dict[str, float] = {}
    if features["h1_aligned"] > 0:
        components["h1_aligned"] = w.h1_aligned
    if features["h1_conflict"] > 0:
        components["h1_conflict"] = w.h1_conflict
    if features["m30_bos"] or features["m30_mss"] or features["m30_choch"] or features["m30_trend"] > 0:
        components["m30_confirmation"] = w.m30_confirmation
    if features["sweep"] > 0:
        components["liquidity_sweep"] = w.liquidity_sweep
        if features["sweep_equal"] > 0:
            components["liquidity_sweep"] += 3.0
    if features["ob_interact"] > 0:
        components["order_block"] = w.order_block
    if features["fvg_interact"] > 0:
        components["fvg"] = w.fvg
    if features["m15_bos"] > 0:
        components["bos"] = w.bos
    if features["m15_choch"] > 0:
        components["choch"] = w.choch
    if features["m15_mss"] > 0:
        components["mss"] = w.mss
    if features["poor_conditions"] > 0:
        components["poor_conditions"] = w.poor_conditions
    elif features["efficiency"] >= 0.30 and 0.8 <= features["atr_ratio"] <= 1.8:
        components["good_conditions"] = w.good_conditions
    total = float(sum(components.values()))
    return total, components


class SetupScorer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
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
                return payload["model"]
            return payload
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
    ) -> ScoreBreakdown:
        features = extract_features(
            direction, h1, m30, m15, conditions, self.settings, sweep, order_block, fvg
        )
        rules, components = rule_score(features, self.settings)
        ml_score: Optional[float] = None
        total = rules
        if self._model is not None:
            vector = feature_vector(features).reshape(1, -1)
            try:
                proba = float(self._model.predict_proba(vector)[0][1])
                ml_score = proba * 100.0
                blend = self.settings.scoring.ml_blend
                total = (1.0 - blend) * rules + blend * ml_score
            except Exception:
                ml_score = None
        return ScoreBreakdown(
            total=total,
            rule_score=rules,
            ml_score=ml_score,
            components=components,
            features=features,
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
    sweep = sweeps[-1] if sweeps else None
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
