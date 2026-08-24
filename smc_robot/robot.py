from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from smc_robot.broker.base import Broker
from smc_robot.config import Settings
from smc_robot.engine import SmcEngine
from smc_robot.manager import PositionManager
from smc_robot.risk.protection import ExecutionGuard

logger = logging.getLogger(__name__)


class SmcRobot:
    def __init__(self, broker: Broker, settings: Settings, dry_run: bool = False):
        self.broker = broker
        self.settings = settings
        self.dry_run = dry_run
        self.engine = SmcEngine(settings)
        self.manager = PositionManager(broker, settings)
        self.guard = ExecutionGuard(settings)
        self._last_bar_time: datetime | None = None

    def run_forever(self) -> None:
        self.broker.connect()
        logger.info(
            "SMC robot started symbol=%s dry_run=%s",
            self.settings.symbol,
            self.dry_run,
        )
        try:
            while True:
                try:
                    self.step()
                except Exception:
                    logger.exception("Robot step failed")
                time.sleep(self.settings.robot.poll_seconds)
        except KeyboardInterrupt:
            logger.info("Robot stopped")
        finally:
            self.broker.shutdown()

    def step(self) -> str:
        symbol = self.settings.symbol
        spec = self.broker.symbol_spec(symbol)
        quote = self.broker.quote(symbol)
        self.guard.observe(quote.spread_points)
        self.manager.manage(symbol, quote)

        if not self.manager.can_enter(symbol):
            return "manage_open_position"

        if self.settings.robot.analyze_on_closed_bar_only:
            m15_probe = self.broker.candles(symbol, "M15", 3)
            if not m15_probe:
                return "no_data"
            bar_time = m15_probe[-1].time
            if self._last_bar_time is not None and bar_time <= self._last_bar_time:
                return "wait_new_bar"
            self._last_bar_time = bar_time

        ok, reason = self.guard.check(quote, spec)
        if not ok:
            logger.warning("Execution blocked: %s", reason)
            return f"blocked:{reason}"

        h1 = self.broker.candles(symbol, "H1", self.settings.bars.h1)
        m30 = self.broker.candles(symbol, "M30", self.settings.bars.m30)
        m15 = self.broker.candles(symbol, "M15", self.settings.bars.m15)
        if self.settings.robot.analyze_on_closed_bar_only:
            h1, m30, m15 = h1[:-1] or h1, m30[:-1] or m30, m15[:-1] or m15

        decision = self.engine.evaluate(
            h1,
            m30,
            m15,
            quote,
            spec,
            self.broker.account_balance(),
            self.guard.recent_spreads(),
        )
        logger.info("Decision action=%s reason=%s", decision.action, decision.reason)
        if decision.signal is None:
            return decision.reason

        signal = decision.signal
        plan = signal.plan
        if self.dry_run:
            logger.info(
                "DRY RUN %s lots=%.2f entry=%.3f sl=%.3f tp=%.3f score=%.1f",
                plan.direction.value,
                plan.lots,
                plan.entry,
                plan.sl,
                plan.tp,
                signal.score.total,
            )
            return "dry_run_signal"

        position = self.broker.market_order(
            symbol=symbol,
            direction=plan.direction,
            lots=plan.lots,
            sl=plan.sl,
            tp=plan.tp,
            deviation_points=int(self.settings.protection.max_slippage_points),
            magic=self.settings.risk.magic,
            comment=self.settings.risk.comment,
        )
        logger.info("Order filled ticket=%s entry=%.3f", position.ticket, position.entry)
        return "order_sent"


def configure_logging(log_dir: str) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(Path(log_dir) / "smc_robot.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
