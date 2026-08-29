"""Market-condition analysis used as a scoring input, not a news filter.

The robot continues to trade through news. Conditions only flag whether
the tape is too choppy or the spread is too hostile for a clean SMC setup.

Rules
-----
ATR ratio = ATR(14) / ATR_slow(50)
    low volatility  when ratio < low_atr_ratio
    extreme vol     when ratio > high_atr_ratio

Efficiency ratio (Kaufman-style over 14 bars):
    abs(close[-1] - open[-14]) / sum(high-low)
    choppy when efficiency is low AND ATR is not expanded (a pullback into
    an order block after displacement is not treated as a dead range)

Spread ratio = current_spread / max(median recent spread, point)
    hostile when spread exceeds protection limits (handled in execution)
    or when spread_ratio >= spread_spike_mult

poor = choppy OR low volatility OR extreme volatility OR hostile spread
"""

from __future__ import annotations

import numpy as np

from smc_robot.config import Settings
from smc_robot.models import Candle, MarketConditions, PremiumDiscount, SessionName
from smc_robot.smc.displacement import detect_displacement
from smc_robot.smc.indicators import atr, efficiency_ratio
from smc_robot.smc.sessions import classify_session


def analyze_conditions(
    candles: list[Candle],
    settings: Settings,
    spread: float,
    recent_spreads: list[float] | None = None,
) -> MarketConditions:
    cfg = settings.market_conditions
    current_atr = atr(candles, settings.smc.atr_period)
    slow_atr = atr(candles, cfg.atr_slow_period)
    atr_ratio = (current_atr / slow_atr) if slow_atr > 0 else 1.0
    efficiency = efficiency_ratio(candles, settings.smc.atr_period)

    median_spread = float(np.median(recent_spreads)) if recent_spreads else spread
    spread_ratio = (spread / median_spread) if median_spread > 0 else 1.0

    reasons: list[str] = []
    choppy = efficiency < cfg.choppy_efficiency and atr_ratio <= 1.05
    low_vol = atr_ratio < cfg.low_atr_ratio
    extreme = atr_ratio > cfg.high_atr_ratio
    hostile_spread = spread_ratio >= settings.protection.spread_spike_mult
    if choppy:
        reasons.append("choppy_efficiency")
    if low_vol:
        reasons.append("low_volatility")
    if extreme:
        reasons.append("extreme_volatility")
    if hostile_spread:
        reasons.append("spread_spike")

    poor = bool(reasons)
    session = SessionName.OFF
    if candles:
        session = classify_session(candles[-1].time, settings.sessions)
    displacement = detect_displacement(
        candles,
        settings.smc.atr_period,
        settings.smc.displacement_body_atr,
    )
    return MarketConditions(
        atr=current_atr,
        atr_ratio=atr_ratio,
        efficiency=efficiency,
        spread=spread,
        spread_ratio=spread_ratio,
        choppy=choppy,
        extreme_volatility=extreme,
        low_volatility=low_vol,
        high_volatility=atr_ratio > 1.40,
        poor=poor,
        reasons=reasons,
        session=session,
        displacement=displacement,
        premium_discount=PremiumDiscount(),
    )
