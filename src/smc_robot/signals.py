"""Multi-timeframe SMC confluence: H1 bias + M15/M5/H1 OB + FVG entries."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from smc_robot.config import RobotConfig
from smc_robot.risk import apply_rr
from smc_robot.smc.fvg import detect_fvgs, unmitigated
from smc_robot.smc.models import FairValueGap, OrderBlock, StructureEvent, TradeSetup
from smc_robot.smc.order_blocks import detect_order_blocks, unmitigated_blocks
from smc_robot.smc.structure import current_bias, detect_structure


@dataclass(slots=True)
class TimeframeSnapshot:
    timeframe: str
    events: list[StructureEvent]
    blocks: list[OrderBlock]
    gaps: list[FairValueGap]
    bias: str | None
    last_close: float
    last_index: int


def analyze_timeframe(df: pd.DataFrame, timeframe: str, config: RobotConfig) -> TimeframeSnapshot:
    events = detect_structure(
        df,
        swing_length=config.swing_length,
        close_break=config.close_break,
        displacement_body_atr=config.displacement_body_atr,
    )
    blocks = detect_order_blocks(
        df,
        events=events,
        lookback=config.ob_lookback,
        swing_length=config.swing_length,
        close_break=config.close_break,
        displacement_body_atr=config.displacement_body_atr,
    )
    gaps = detect_fvgs(df, min_size=config.fvg_min_size)
    last_index = len(df) - 1
    last_close = float(df.iloc[last_index]["close"]) if last_index >= 0 else 0.0
    return TimeframeSnapshot(
        timeframe=timeframe,
        events=events,
        blocks=blocks,
        gaps=gaps,
        bias=current_bias(events),
        last_close=last_close,
        last_index=last_index,
    )


def _score_setup(
    *,
    htf_aligned: bool,
    event: StructureEvent,
    in_ob: bool,
    in_fvg: bool,
    recent_mss: bool,
) -> int:
    score = 0
    if htf_aligned:
        score += 25
    if event.kind == "MSS":
        score += 25
    elif event.kind == "CHOCH":
        score += 18
    elif event.kind == "BOS":
        score += 12
    if event.displacement:
        score += 10
    if in_ob:
        score += 20
    if in_fvg:
        score += 20
    if recent_mss:
        score += 5
    return min(score, 100)


def _sl_from_zone(
    side: str,
    entry: float,
    ob: OrderBlock | None,
    fvg: FairValueGap | None,
    df: pd.DataFrame,
    swing_length: int,
) -> float:
    """Invalidation is just beyond the Order Block / FVG being traded."""
    pad = 0.05
    del df, swing_length
    if side == "buy":
        floors = []
        if ob:
            floors.append(ob.bottom)
        if fvg:
            floors.append(fvg.bottom)
        return (min(floors) if floors else entry) - pad
    ceilings = []
    if ob:
        ceilings.append(ob.top)
    if fvg:
        ceilings.append(fvg.top)
    return (max(ceilings) if ceilings else entry) + pad


def _taps_zone(low: float, high: float, bottom: float, top: float) -> bool:
    return high >= bottom and low <= top


def _nearest(zones: list, price: float):
    return min(zones, key=lambda z: abs(z.midpoint - price)) if zones else None


def _active_zone(
    df: pd.DataFrame,
    snapshot: TimeframeSnapshot,
    direction: str,
) -> tuple[OrderBlock | None, FairValueGap | None, bool, bool]:
    """Prefer the unmitigated OB / FVG that the last bar actually tapped."""
    i = snapshot.last_index
    low = float(df.at[i, "low"])
    high = float(df.at[i, "high"])
    price = snapshot.last_close
    blocks = unmitigated_blocks(snapshot.blocks, direction=direction)
    gaps = unmitigated(snapshot.gaps, direction=direction)
    tapped_obs = [b for b in blocks if _taps_zone(low, high, b.bottom, b.top)]
    tapped_fvgs = [g for g in gaps if _taps_zone(low, high, g.bottom, g.top)]
    ob = _nearest(tapped_obs, price)
    fvg = _nearest(tapped_fvgs, price)
    return ob, fvg, ob is not None, fvg is not None


def build_setup(
    df: pd.DataFrame,
    snapshot: TimeframeSnapshot,
    config: RobotConfig,
    htf_bias: str | None,
) -> TradeSetup | None:
    if not snapshot.events or snapshot.bias is None:
        return None
    if htf_bias and snapshot.bias != htf_bias:
        return None

    event = snapshot.events[-1]
    direction = snapshot.bias
    ob, fvg, in_ob, in_fvg = _active_zone(df, snapshot, direction)
    if not (in_ob or in_fvg):
        return None

    price = snapshot.last_close

    side = "buy" if direction == "bullish" else "sell"
    sl = _sl_from_zone(side, price, ob, fvg, df, config.swing_length)
    recent_mss = any(e.kind == "MSS" and e.direction == direction for e in snapshot.events[-3:])
    score = _score_setup(
        htf_aligned=htf_bias is None or snapshot.bias == htf_bias,
        event=event,
        in_ob=in_ob,
        in_fvg=in_fvg,
        recent_mss=recent_mss,
    )
    if score < config.min_confluence_score:
        return None

    setup = TradeSetup(
        timeframe=snapshot.timeframe,
        side=side,
        entry=price,
        sl=sl,
        tp=price,
        score=score,
        reason=_reason(event, in_ob, in_fvg, htf_bias),
        event_kind=event.kind,
        ob=ob,
        fvg=fvg,
        bar_index=snapshot.last_index,
    )
    return apply_rr(setup, config.risk_reward)


def _reason(event: StructureEvent, in_ob: bool, in_fvg: bool, htf_bias: str | None) -> str:
    parts = [f"{event.kind} {event.direction}"]
    if in_ob:
        parts.append("order-block retest")
    if in_fvg:
        parts.append("FVG fill")
    if htf_bias:
        parts.append(f"HTF {htf_bias}")
    return " + ".join(parts)


def scan_setups(
    frames: dict[str, pd.DataFrame],
    config: RobotConfig,
) -> list[TradeSetup]:
    """Pick up to three setups — one per M5 / M15 / H1 — aligned with H1 bias."""
    if config.htf_bias not in frames:
        raise KeyError(f"HTF {config.htf_bias} candles are required")

    snapshots = {
        tf: analyze_timeframe(df, tf, config) for tf, df in frames.items()
    }
    htf_bias = snapshots[config.htf_bias].bias
    setups: list[TradeSetup] = []
    for tf in config.entry_timeframes:
        if tf not in snapshots:
            continue
        setup = build_setup(frames[tf], snapshots[tf], config, htf_bias)
        if setup:
            setups.append(setup)
        if len(setups) >= config.max_positions:
            break
    setups.sort(key=lambda s: s.score, reverse=True)
    return setups[: config.max_positions]
