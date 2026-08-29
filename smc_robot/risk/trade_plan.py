from __future__ import annotations

from smc_robot.config import Settings
from smc_robot.models import Direction, LiquiditySweep, TradePlan, Zone
from smc_robot.risk.sizing import (
    SymbolSpec,
    lots_from_balance,
    lots_from_risk_percent,
    normalize_lots,
)


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
    opposing_liquidity: float | None = None,
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
        tp, adjusted = _respect_obstacle(tp, opposing_liquidity, direction, entry, risk)
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
        tp, adjusted = _respect_obstacle(tp, opposing_liquidity, direction, entry, risk)

    lots = _choose_lots(balance, risk, spec, settings)
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
        risk_amount=balance * (settings.risk.risk_percent / 100.0),
        tp_adjusted=adjusted,
    )


def _choose_lots(equity: float, sl_distance: float, spec: SymbolSpec, settings: Settings) -> float:
    mode = settings.risk.sizing_mode
    if mode == "balance_step":
        lots = lots_from_balance(
            equity,
            spec,
            settings.risk.balance_per_lot_step,
            settings.risk.lot_step_per_balance,
        )
    else:
        lots = lots_from_risk_percent(
            equity,
            settings.risk.risk_percent,
            sl_distance,
            spec,
            min_lot=settings.risk.min_lot,
            max_lot=settings.risk.max_lot,
        )
        if lots <= 0:
            lots = lots_from_balance(
                equity,
                spec,
                settings.risk.balance_per_lot_step,
                settings.risk.lot_step_per_balance,
            )
    lots = min(lots, settings.risk.max_lot)
    return normalize_lots(lots, spec)


def _respect_obstacle(
    tp: float,
    obstacle: float | None,
    direction: Direction,
    entry: float,
    risk: float,
) -> tuple[float, bool]:
    if obstacle is None or risk <= 0:
        return tp, False
    min_r = 1.2
    if direction == Direction.BUY:
        if obstacle <= entry:
            return tp, False
        if tp > obstacle:
            clipped = obstacle - max(risk * 0.05, 0.01)
            if clipped - entry >= min_r * risk:
                return clipped, True
        return tp, False
    if obstacle >= entry:
        return tp, False
    if tp < obstacle:
        clipped = obstacle + max(risk * 0.05, 0.01)
        if entry - clipped >= min_r * risk:
            return clipped, True
    return tp, False
