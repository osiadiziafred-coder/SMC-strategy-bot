"""Lot sizing, 1:2 SL/TP, and trailing stop (XL) management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from smc_robot.config import RobotConfig
from smc_robot.smc.models import TradeSetup

Side = Literal["buy", "sell"]


def lot_size(balance: float, config: RobotConfig | None = None) -> float:
    """0.01 lot from any starting balance; add 0.01 for every extra $300.

    Examples with default config:
        $50   -> 0.01
        $300  -> 0.01
        $600  -> 0.02
        $900  -> 0.03
        $1500 -> 0.05
    """
    cfg = config or RobotConfig()
    if balance <= 0:
        return 0.0
    steps = int(balance // 300)
    lots = max(cfg.min_lot, steps * cfg.lot_per_300_usd)
    # "Started from any amount" — below $300 still trades min lot.
    if steps == 0:
        lots = cfg.min_lot
    step = cfg.lot_step or 0.01
    lots = round(round(lots / step) * step, 2)
    return lots


def stops_for_entry(
    side: Side,
    entry: float,
    sl_price: float,
    risk_reward: float = 2.0,
) -> tuple[float, float]:
    """Return (sl, tp) with TP at ``risk_reward`` times the SL distance."""
    risk = abs(entry - sl_price)
    if risk <= 0:
        raise ValueError("stop loss must be away from entry")
    if side == "buy":
        sl = min(sl_price, entry - 1e-9)
        tp = entry + risk * risk_reward
    else:
        sl = max(sl_price, entry + 1e-9)
        tp = entry - risk * risk_reward
    return sl, tp


def apply_rr(setup: TradeSetup, risk_reward: float = 2.0) -> TradeSetup:
    sl, tp = stops_for_entry(setup.side, setup.entry, setup.sl, risk_reward)
    setup.sl = sl
    setup.tp = tp
    return setup


@dataclass(slots=True)
class TrailingState:
    original_sl: float
    original_risk: float
    moved_to_breakeven: bool = False


def trail_stop(
    side: Side,
    entry: float,
    current_sl: float,
    current_price: float,
    original_risk: float,
    config: RobotConfig | None = None,
    already_breakeven: bool = False,
) -> tuple[float, bool]:
    """Move SL with price once the trade is in profit.

    1. At ``trail_activate_r`` (default 1R) move SL to breakeven + buffer.
    2. After that, trail SL *up* on buys (down on sells) by ``trail_distance_r``.
    SL never moves against the trade.
    """
    cfg = config or RobotConfig()
    if original_risk <= 0:
        return current_sl, already_breakeven

    if side == "buy":
        open_profit = current_price - entry
    else:
        open_profit = entry - current_price
    r_multiple = open_profit / original_risk

    new_sl = current_sl
    be = already_breakeven

    if cfg.trail_to_breakeven and r_multiple >= cfg.trail_activate_r:
        if side == "buy":
            candidate = entry + cfg.breakeven_buffer
            new_sl = max(new_sl, candidate)
        else:
            candidate = entry - cfg.breakeven_buffer
            new_sl = min(new_sl, candidate)
        be = True

    if be and r_multiple >= cfg.trail_activate_r:
        trail_dist = original_risk * cfg.trail_distance_r
        if side == "buy":
            candidate = current_price - trail_dist
            # Only trail up, and never past current price.
            if candidate > new_sl and candidate < current_price:
                new_sl = candidate
        else:
            candidate = current_price + trail_dist
            if candidate < new_sl and candidate > current_price:
                new_sl = candidate

    return new_sl, be
