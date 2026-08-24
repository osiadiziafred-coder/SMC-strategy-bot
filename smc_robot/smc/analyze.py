from __future__ import annotations

from dataclasses import dataclass, field

from smc_robot.config import Settings
from smc_robot.models import (
    Candle,
    LiquiditySweep,
    StructureEvent,
    Swing,
    Trend,
    Zone,
)
from smc_robot.smc.fvg import detect_fvgs, unfilled_fvgs
from smc_robot.smc.liquidity import (
    LiquidityPool,
    build_liquidity_pools,
    detect_sweeps,
    liquidity_zones,
)
from smc_robot.smc.order_blocks import annotate_mitigation, detect_order_blocks
from smc_robot.smc.structure import detect_structure_events


@dataclass
class TimeframeAnalysis:
    candles: list[Candle]
    trend: Trend
    internal_swings: list[Swing]
    external_swings: list[Swing]
    events: list[StructureEvent]
    order_blocks: list[Zone]
    fvgs: list[Zone]
    pools: list[LiquidityPool] = field(default_factory=list)
    sweeps: list[LiquiditySweep] = field(default_factory=list)
    liquidity_zones: list[Zone] = field(default_factory=list)


def analyze_timeframe(candles: list[Candle], settings: Settings) -> TimeframeAnalysis:
    smc = settings.smc
    events, trend, internal, external = detect_structure_events(
        candles, smc.swing_n_internal, smc.swing_n_external
    )
    raw_obs = detect_order_blocks(
        candles,
        events,
        lookback=smc.ob_lookback_bars,
        impulse_atr_mult=smc.ob_impulse_atr_mult,
        atr_period=smc.atr_period,
    )
    order_blocks = annotate_mitigation(candles, raw_obs)
    fvgs = unfilled_fvgs(
        candles, detect_fvgs(candles, smc.fvg_min_atr_mult, smc.atr_period)
    )
    pools = build_liquidity_pools(
        internal, candles, smc.equal_level_atr_mult, smc.atr_period
    )
    sweeps = detect_sweeps(candles, pools)
    zones = liquidity_zones(pools, candles, smc.atr_period)
    return TimeframeAnalysis(
        candles=candles,
        trend=trend,
        internal_swings=internal,
        external_swings=external,
        events=events,
        order_blocks=order_blocks,
        fvgs=fvgs,
        pools=pools,
        sweeps=sweeps,
        liquidity_zones=zones,
    )
