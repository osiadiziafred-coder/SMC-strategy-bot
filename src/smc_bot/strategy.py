"""SMC trading strategy.

The strategy converts detected market structure into concrete trade setups:

1. Detect BOS / CHoCH structural breaks.
2. For each break, locate the order block that produced the impulsive move.
3. Create a pending setup that enters when price retraces into that order block,
   with a protective stop beyond the block and a take-profit at a fixed
   risk-to-reward multiple.

The strategy only *describes* setups; filling and exits are simulated by
:mod:`smc_bot.backtester`, keeping the trading logic easy to unit test.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import Direction, OrderBlock, detect_structure, find_order_block


@dataclass(frozen=True)
class StrategyConfig:
    swing_lookback: int = 3
    risk_reward: float = 2.0
    stop_buffer_frac: float = 0.10  # extra room beyond the order block, as a fraction of its height
    max_setup_age: int = 60  # bars a pending setup stays valid before expiring
    only_choch: bool = False  # if True, trade reversals (CHoCH) only


@dataclass(frozen=True)
class TradeSetup:
    direction: Direction
    active_from: int
    expires_at: int
    entry: float
    stop_loss: float
    take_profit: float
    order_block: OrderBlock

    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop_loss)

    @property
    def reward(self) -> float:
        return abs(self.take_profit - self.entry)


def build_setups(df: pd.DataFrame, config: StrategyConfig | None = None) -> list[TradeSetup]:
    """Build the list of trade setups implied by the SMC structure of ``df``."""

    config = config or StrategyConfig()
    events = detect_structure(df, lookback=config.swing_lookback)
    setups: list[TradeSetup] = []

    for event in events:
        if config.only_choch and event.event != "CHoCH":
            continue

        ob = find_order_block(df, break_index=event.index, direction=event.direction)
        if ob is None:
            continue

        height = ob.top - ob.bottom
        if height <= 0:
            continue
        buffer = height * config.stop_buffer_frac

        if event.direction == Direction.BULLISH:
            entry = ob.top
            stop_loss = ob.bottom - buffer
            take_profit = entry + config.risk_reward * (entry - stop_loss)
        else:
            entry = ob.bottom
            stop_loss = ob.top + buffer
            take_profit = entry - config.risk_reward * (stop_loss - entry)

        setups.append(
            TradeSetup(
                direction=event.direction,
                active_from=event.index,
                expires_at=event.index + config.max_setup_age,
                entry=round(entry, 5),
                stop_loss=round(stop_loss, 5),
                take_profit=round(take_profit, 5),
                order_block=ob,
            )
        )

    return setups
