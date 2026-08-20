"""SMC XAUUSDm Trading Robot — main entry point."""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime

from broker import Broker
from config import DEFAULT_CONFIG, Config
from risk_manager import RiskManager
from strategy import SMCStrategy

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(config: Config) -> None:
  fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
  handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
  if config.log_file:
    handlers.append(logging.FileHandler(config.log_file))
  logging.basicConfig(level=getattr(logging, config.log_level), format=fmt, handlers=handlers)


logger = logging.getLogger("smc_robot")

# ---------------------------------------------------------------------------
# Robot
# ---------------------------------------------------------------------------

class SMCRobot:
  """Orchestrates scanning, signal generation, order execution, and management."""

  def __init__(self, config: Config | None = None) -> None:
    self.config = config or DEFAULT_CONFIG
    self.broker = Broker(self.config)
    self.risk = RiskManager(self.config, self.broker)
    self.strategy = SMCStrategy(self.config)
    self._running = False

  def start(self) -> None:
    setup_logging(self.config)
    logger.info("=" * 60)
    logger.info("SMC XAUUSDm Robot starting — %s", datetime.utcnow().isoformat())
    logger.info("Symbol: %s | R:R 1:%.0f | Breakeven at %.0fR",
                self.config.symbol,
                self.config.risk_reward_ratio,
                self.config.breakeven_at_r)
    logger.info("Timeframes: H1 (bias) / M15 (structure) / M5 (entry)")
    logger.info("=" * 60)

    if not self.broker.connect():
      logger.error("Failed to connect to MetaTrader 5. Exiting.")
      sys.exit(1)

    self._running = True
    signal.signal(signal.SIGINT, self._handle_shutdown)
    signal.signal(signal.SIGTERM, self._handle_shutdown)

    try:
      self._run_loop()
    finally:
      self.broker.disconnect()
      logger.info("Robot stopped.")

  def _handle_shutdown(self, signum: int, frame: object) -> None:
    logger.info("Shutdown signal received (%d)", signum)
    self._running = False

  def _run_loop(self) -> None:
    while self._running:
      try:
        self._tick()
      except Exception:
        logger.exception("Error in main loop")
      time.sleep(self.config.scan_interval_seconds)

  def _tick(self) -> None:
    # --- Manage open positions (breakeven) ---
    positions = self.broker.get_open_positions()
    for pos in positions:
      self.risk.move_to_breakeven(pos)

    # --- Only scan for new entries if slot is free ---
    if not self.risk.can_open_new_trade():
      logger.debug("Max positions open (%d) — skipping scan", self.config.max_open_positions)
      return

    # --- Fetch multi-timeframe data ---
    df_h1 = self.broker.get_candles(self.config.bias_tf, self.config.candle_bars_h1)
    df_m15 = self.broker.get_candles(self.config.structure_tf, self.config.candle_bars_m15)
    df_m5 = self.broker.get_candles(self.config.entry_tf, self.config.candle_bars_m5)

    if df_h1.empty or df_m15.empty or df_m5.empty:
      logger.warning("Missing candle data — retrying next cycle")
      return

    # --- Run strategy ---
    signal = self.strategy.analyze(df_h1, df_m15, df_m5)
    if signal is None:
      return

    logger.info("SIGNAL: %s | %s", signal.direction.upper(), signal.reason)

    # --- Build trade plan and execute ---
    try:
      plan = self.risk.build_trade_plan(
        direction=signal.direction,
        entry_price=signal.entry_price,
        sl_price=signal.sl_price,
      )
    except ValueError as exc:
      logger.error("Invalid trade plan: %s", exc)
      return

    logger.info(
      "Trade plan: %s %.2f lots | Entry ~%.2f | SL %.2f | TP %.2f (1:%.0f R:R)",
      plan.direction.upper(),
      plan.volume,
      plan.entry_price,
      plan.sl,
      plan.tp,
      self.config.risk_reward_ratio,
    )

    result = self.broker.place_order(
      direction=plan.direction,
      volume=plan.volume,
      sl=plan.sl,
      tp=plan.tp,
      comment=plan.comment,
    )

    if not result.success:
      logger.error("Order failed: %s", result.message)
    else:
      logger.info("Trade opened — ticket %d", result.ticket)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
  robot = SMCRobot()
  robot.start()


if __name__ == "__main__":
  main()
