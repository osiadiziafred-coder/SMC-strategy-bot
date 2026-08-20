"""Risk management: lot sizing, SL/TP calculation, breakeven."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from broker import Broker, Position
from config import Config

logger = logging.getLogger(__name__)


@dataclass
class TradePlan:
  direction: str  # "buy" or "sell"
  entry_price: float
  sl: float
  tp: float
  volume: float
  risk_distance: float  # 1R in price units
  comment: str = "SMC_Robot"


class RiskManager:
  def __init__(self, config: Config, broker: Broker) -> None:
    self.config = config
    self.broker = broker

  def calculate_lot_size(self) -> float:
    balance = self.broker.get_balance()
    lots = self.config.lot_size_for_balance(balance)
    logger.debug("Balance %.2f → lot size %.2f", balance, lots)
    return lots

  def build_trade_plan(
    self,
    direction: str,
    entry_price: float,
    sl_price: float,
  ) -> TradePlan:
    """Build a trade with 1:2 R:R based on SL distance."""
    risk_distance = abs(entry_price - sl_price)
    if risk_distance <= 0:
      raise ValueError("SL must be different from entry price")

    reward_distance = risk_distance * self.config.risk_reward_ratio

    if direction == "buy":
      tp = entry_price + reward_distance
    else:
      tp = entry_price - reward_distance

    volume = self.calculate_lot_size()

    return TradePlan(
      direction=direction,
      entry_price=entry_price,
      sl=sl_price,
      tp=tp,
      volume=volume,
      risk_distance=risk_distance,
    )

  def should_move_to_breakeven(self, position: Position) -> bool:
    """Return True if price has reached breakeven_at_r and SL is not yet at entry."""
    bid, ask = self.broker.current_price()
    entry = position.entry_price

    # Estimate 1R from current SL distance
    risk_distance = abs(entry - position.sl)
    if risk_distance <= 0:
      return False

    trigger_distance = risk_distance * self.config.breakeven_at_r

    if position.direction == "buy":
      current = bid
      target = entry + trigger_distance
      sl_at_be = abs(position.sl - entry) < self.config.pip_size * 0.5
      return current >= target and not sl_at_be
    else:
      current = ask
      target = entry - trigger_distance
      sl_at_be = abs(position.sl - entry) < self.config.pip_size * 0.5
      return current <= target and not sl_at_be

  def move_to_breakeven(self, position: Position) -> bool:
    if not self.should_move_to_breakeven(position):
      return False

    result = self.broker.modify_sl(position.ticket, position.entry_price)
    if result.success:
      logger.info(
        "Breakeven activated for ticket %d at %.2f",
        position.ticket,
        position.entry_price,
      )
    else:
      logger.warning("Breakeven failed for ticket %d: %s", position.ticket, result.message)
    return result.success

  def can_open_new_trade(self) -> bool:
    positions = self.broker.get_open_positions()
    return len(positions) < self.config.max_open_positions
