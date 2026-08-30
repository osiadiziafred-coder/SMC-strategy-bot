from __future__ import annotations

import logging
import time
from datetime import datetime

from smc_robot.broker.base import Broker
from smc_robot.bridge import FileBridge
from smc_robot.config import Settings
from smc_robot.engine import SmcEngine
from smc_robot.journal import DecisionJournal
from smc_robot.logger import configure_logging
from smc_robot.manager import PositionManager
from smc_robot.models import Direction, SwingKind
from smc_robot.risk.daily import DailyGuard
from smc_robot.risk.protection import ExecutionGuard
from smc_robot.smc.analyze import analyze_timeframe
from smc_robot.smc.swings import last_swings

logger = logging.getLogger(__name__)


class SmcRobot:
    def __init__(
        self,
        broker: Broker,
        settings: Settings,
        dry_run: bool = False,
        use_bridge: bool = False,
    ):
        self.broker = broker
        self.settings = settings
        self.dry_run = dry_run
        self.use_bridge = use_bridge
        self.engine = SmcEngine(settings)
        self.manager = PositionManager(broker, settings)
        self.guard = ExecutionGuard(settings)
        self.daily = DailyGuard(settings)
        self.journal = DecisionJournal(settings.robot.log_dir)
        self.bridge = FileBridge(settings) if use_bridge else None
        self._last_bar_time: datetime | None = None
        self._last_signal_id: str | None = None
        self._known_tickets: set[int] = set()

    def run_forever(self) -> None:
        self.broker.connect()
        logger.info(
            "SMC robot started symbol=%s dry_run=%s bridge=%s",
            self.settings.symbol,
            self.dry_run,
            self.use_bridge,
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
        if self.use_bridge and self.bridge is not None:
            self.bridge.heartbeat()
            if not self.bridge.connected() and self.settings.robot.fail_closed:
                logger.warning("MQL5 bridge disconnected; no new trades")
                return "bridge_disconnected"

        spec = self.broker.symbol_spec(symbol)
        quote = self.broker.quote(symbol)
        self.guard.observe(quote.spread_points)
        equity = self.broker.account_balance()
        self.daily.roll(quote.time, equity)
        self._harvest_closes(symbol)

        m15_live = self.broker.candles(symbol, "M15", max(80, self.settings.bars.m15))
        structure_sl = _structure_trail_price(m15_live, self.settings)
        self.manager.manage(symbol, quote, structure_sl)

        if not self.manager.can_enter(symbol):
            return "manage_open_position"

        allowed, daily_reason = self.daily.allow(equity)
        if not allowed:
            return daily_reason

        if self.settings.robot.analyze_on_closed_bar_only:
            m15_probe = m15_live[-3:] if m15_live else []
            if not m15_probe:
                return "no_data"
            bar_time = m15_probe[-1].time
            if self._last_bar_time is not None and bar_time <= self._last_bar_time:
                return "wait_new_bar"
            self._last_bar_time = bar_time

        bar_index = len(m15_live) - 1 if m15_live else 0
        cooling, cool_reason = self.daily.cooldown_active(bar_index)
        if cooling:
            return cool_reason

        ok, reason = self.guard.check(quote, spec)
        if not ok:
            logger.warning("Execution blocked: %s", reason)
            return f"blocked:{reason}"

        h1 = self.broker.candles(symbol, "H1", self.settings.bars.h1)
        m30 = self.broker.candles(symbol, "M30", self.settings.bars.m30)
        m15 = self.broker.candles(symbol, "M15", self.settings.bars.m15)
        if self.settings.robot.analyze_on_closed_bar_only:
            h1, m30, m15 = h1[:-1] or h1, m30[:-1] or m30, m15[:-1] or m15
        if not h1 or not m30 or not m15:
            return "incomplete_market_data"

        decision = self.engine.evaluate(
            h1,
            m30,
            m15,
            quote,
            spec,
            equity,
            self.guard.recent_spreads(),
        )
        self.journal.write(symbol, decision, quote.spread_points)
        logger.info("Decision action=%s reason=%s", decision.action, decision.reason)
        if decision.signal is None:
            return decision.reason

        signal = decision.signal
        if self.daily.last_was_loss and self.settings.cooldown.stronger_after_loss:
            if signal.grade.value != self.settings.cooldown.loss_min_grade:
                return "stronger_setup_required_after_loss"
            if signal.score.ml_probability is not None:
                need = self.settings.scoring.ml_min_probability + self.settings.cooldown.loss_ml_boost
                if signal.score.ml_probability < need:
                    return "ml_boost_required_after_loss"

        if signal.signal_id == self._last_signal_id:
            return "duplicate_signal"
        self._last_signal_id = signal.signal_id

        plan = signal.plan
        if self.dry_run:
            logger.info(
                "DRY RUN %s lots=%.2f entry=%.3f sl=%.3f tp=%.3f score=%.1f id=%s",
                plan.direction.value,
                plan.lots,
                plan.entry,
                plan.sl,
                plan.tp,
                signal.score.total,
                signal.signal_id,
            )
            return "dry_run_signal"

        if self.use_bridge and self.bridge is not None:
            cmd_id = self.bridge.send_signal(signal)
            result = self.bridge.wait_for_result(
                cmd_id, timeout=self.settings.bridge.result_timeout_seconds
            )
            if not result:
                self.journal.write_outcome(
                    symbol, decision, result="timeout", rejection_reason="bridge_no_result"
                )
                logger.warning("Bridge did not confirm command %s", cmd_id)
                return "bridge_no_result"
            if not result.get("ok"):
                err = str(result.get("error") or "rejected")
                self.journal.write_outcome(
                    symbol, decision, result="rejected", rejection_reason=err
                )
                logger.warning("Bridge rejected %s: %s", cmd_id, err)
                return f"bridge_rejected:{err}"
            ticket = int(result.get("ticket") or 0)
            if ticket:
                self._known_tickets.add(ticket)
            fill = result.get("price")
            self.journal.write_outcome(
                symbol,
                decision,
                result="filled",
                fill_price=float(fill) if fill is not None else None,
            )
            logger.info("Bridge filled ticket=%s price=%s", ticket, fill)
            return "bridge_command_filled"

        position = self.broker.market_order(
            symbol=symbol,
            direction=plan.direction,
            lots=plan.lots,
            sl=plan.sl,
            tp=plan.tp,
            deviation_points=int(self.settings.protection.max_slippage_points),
            magic=self.settings.risk.magic,
            comment=(self.settings.risk.comment + "-" + signal.signal_id)[:31],
        )
        self._known_tickets.add(position.ticket)
        logger.info("Order filled ticket=%s entry=%.3f", position.ticket, position.entry)
        return "order_sent"

    def _harvest_closes(self, symbol: str) -> None:
        open_now = {p.ticket for p in self.broker.open_positions(symbol, self.settings.risk.magic)}
        missing = self._known_tickets - open_now
        if not missing:
            self._known_tickets |= open_now
            return
        quote = self.broker.quote(symbol)
        m15 = self.broker.candles(symbol, "M15", 5)
        bar_index = len(m15) - 1 if m15 else 0
        for _ticket in missing:
            self.daily.record_close(0.0, bar_index)
        self._known_tickets = open_now
        _ = quote


def _structure_trail_price(candles, settings: Settings) -> float | None:
    if len(candles) < 20:
        return None
    analysis = analyze_timeframe(candles, settings)
    last = len(analysis.candles) - 1
    if analysis.trend.value == "BULLISH":
        lows = last_swings(analysis.internal_swings, SwingKind.LOW, last, 1)
        return lows[-1].price if lows else None
    if analysis.trend.value == "BEARISH":
        highs = last_swings(analysis.internal_swings, SwingKind.HIGH, last, 1)
        return highs[-1].price if highs else None
    return None


__all__ = ["SmcRobot", "configure_logging"]
