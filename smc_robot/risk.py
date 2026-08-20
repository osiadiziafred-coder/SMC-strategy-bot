from __future__ import annotations

import math

from smc_robot.config import Position, RobotConfig, Side


def lot_size(balance: float, config: RobotConfig | None = None) -> float:
    """0.01 lots for every $100 of balance.

    Any positive balance can start trading: if the calculated size is below
    `min_lot`, the robot uses `min_lot` (typically 0.01).
    """
    cfg = config or RobotConfig()
    if balance <= 0:
        return 0.0
    raw = (balance / 100.0) * cfg.lot_per_100
    stepped = math.floor(raw / cfg.lot_step + 1e-12) * cfg.lot_step
    if stepped < cfg.min_lot:
        stepped = cfg.min_lot
    stepped = min(stepped, cfg.max_lot)
    return round(stepped, 2)


def take_profit(entry: float, sl: float, side: Side, risk_reward: float = 2.0) -> float:
    risk = abs(entry - sl)
    if side == "buy":
        return entry + risk * risk_reward
    return entry - risk * risk_reward


def r_multiple(position: Position, price: float) -> float:
    risk = position.risk
    if risk <= 0:
        return 0.0
    if position.side == "buy":
        return (price - position.entry) / risk
    return (position.entry - price) / risk


def trailing_stop(position: Position, price: float, config: RobotConfig | None = None) -> float:
    """Move SL in the trade's favor as price advances.

    At +1R the stop is lifted to breakeven. After that the stop trails at
    `trail_distance_r` behind price, so a long SL only ratchets upward.
    """
    cfg = config or RobotConfig()
    risk = position.risk
    if risk <= 0:
        return position.sl

    profit_r = r_multiple(position, price)
    new_sl = position.sl
    if profit_r >= cfg.breakeven_at_r:
        locked_r = max(0.0, profit_r - cfg.trail_distance_r)
        if position.side == "buy":
            candidate = position.entry + locked_r * risk
            new_sl = max(position.sl, candidate, position.entry)
        else:
            candidate = position.entry - locked_r * risk
            new_sl = min(position.sl, candidate, position.entry)
    return new_sl


def hit_stop_or_target(position: Position, high: float, low: float) -> str | None:
    if position.side == "buy":
        if low <= position.sl:
            return "sl"
        if high >= position.tp:
            return "tp"
        return None
    if high >= position.sl:
        return "sl"
    if low <= position.tp:
        return "tp"
    return None
