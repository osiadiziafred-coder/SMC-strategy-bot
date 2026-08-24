from __future__ import annotations

from smc_robot.config import Settings
from smc_robot.models import Direction, LiquiditySweep, TradePlan, Zone
from smc_robot.risk.sizing import SymbolSpec, lots_from_balance


def build_trade_plan(
    direction: Direction,
    entry: float,
    sweep: LiquiditySweep | None,
    order_block: Zone | None,
    fvg: Zone | None,
    atr_value: float,
    balance: float,
    spec: SymbolSpec,
    settings: Settings,
) -> TradePlan | None:
    buffer = settings.risk.sl_buffer_atr_mult * atr_value
    min_stop = settings.protection.min_stop_points * spec.point
    stops_level = spec.trade_stops_level * spec.point
    min_distance = max(min_stop, stops_level, spec.point)

    sl_source = "structure"
    if direction == Direction.BUY:
        candidates: list[tuple[str, float]] = []
        if sweep is not None:
            candidates.append(("sweep_low", sweep.wick))
        if order_block is not None:
            candidates.append(("order_block", order_block.low))
        if fvg is not None:
            candidates.append(("fvg", fvg.low))
        if not candidates:
            return None
        sl_source, structural = min(candidates, key=lambda item: item[1])
        sl = structural - buffer
        if entry - sl < min_distance:
            sl = entry - min_distance
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + settings.risk.reward_ratio * risk
    else:
        candidates = []
        if sweep is not None:
            candidates.append(("sweep_high", sweep.wick))
        if order_block is not None:
            candidates.append(("order_block", order_block.high))
        if fvg is not None:
            candidates.append(("fvg", fvg.high))
        if not candidates:
            return None
        sl_source, structural = max(candidates, key=lambda item: item[1])
        sl = structural + buffer
        if sl - entry < min_distance:
            sl = entry + min_distance
        risk = sl - entry
        if risk <= 0:
            return None
        tp = entry - settings.risk.reward_ratio * risk

    lots = lots_from_balance(
        balance,
        spec,
        settings.risk.balance_per_lot_step,
        settings.risk.lot_step_per_balance,
    )
    if lots <= 0:
        return None
    return TradePlan(
        direction=direction,
        entry=entry,
        sl=sl,
        tp=tp,
        risk=risk,
        lots=lots,
        sl_source=sl_source,
    )
