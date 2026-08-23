from __future__ import annotations

import math

from smc_robot.config import Position, RobotConfig, Side


def lot_size(balance: float, config: RobotConfig | None = None) -> float:
    """0.01 lots for every $100 of account balance.

    $100 → 0.01, $200 → 0.02, $500 → 0.05, $1,000 → 0.10.
    Any positive balance below $100 still uses `min_lot` so a demo can start.
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


def breakeven_stop(position: Position, price: float, config: RobotConfig | None = None) -> float:
    """Once price reaches +1R, move SL to breakeven. Never widen the stop."""
    cfg = config or RobotConfig()
    if r_multiple(position, price) < cfg.breakeven_at_r:
        return position.sl
    if position.side == "buy":
        candidate = position.entry + cfg.breakeven_offset
        return max(position.sl, candidate)
    candidate = position.entry - cfg.breakeven_offset
    return min(position.sl, candidate)


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
