from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from smc_robot.broker.base import Broker
from smc_robot.config import Evaluation, Position, RobotConfig, Signal
from smc_robot.news import NewsFilter
from smc_robot.risk import breakeven_stop, lot_size
from smc_robot.smc.strategy import SmcStrategy

logger = logging.getLogger(__name__)


class SmcRobot:
    """FredFx v1 SMC: one XAUUSDm position, sequential H1→M15→M5 entries."""

    def __init__(self, broker: Broker, config: RobotConfig | None = None) -> None:
        self.broker = broker
        self.config = config or RobotConfig()
        self.config.validate()
        self.strategy = SmcStrategy(self.config)
        self.news = NewsFilter(self.config)
        self.trades_today = 0
        self._today: date | None = None
        self.signals: list[Signal] = []
        self.last_evaluation: Evaluation | None = None
        self.initial_stops: dict[int, float] = {}
        self._had_position = False
        self._cooldown_left = 0

    def start(self) -> None:
        self.broker.connect()
        logger.info("%s connected for %s", self.config.robot_name, self.config.symbol)

    def stop(self) -> None:
        self.broker.shutdown()

    def on_bar(self) -> Signal | None:
        self._roll_day()
        self._manage_open_trade()
        open_positions = self.broker.open_positions(self.config.magic)
        if self._had_position and not open_positions:
            self._cooldown_left = self.config.cooldown_bars
        self._had_position = bool(open_positions)
        if open_positions:
            return None
        if self._cooldown_left > 0:
            self._cooldown_left -= 1
            return None
        if self.config.max_trades_per_day is not None and self.trades_today >= self.config.max_trades_per_day:
            return None
        if self.news.is_blocked(self._bar_time()):
            event = self.news.blocking_event(self._bar_time())
            title = event.title if event else "news"
            logger.info("Skipping new entries around news: %s", title)
            return None
        signal = self._scan()
        if signal is None:
            return None
        self._enter(signal)
        return signal

    def run_until_end(self) -> list[Signal]:
        """Drive a PaperBroker from the current index to the last bar."""
        from smc_robot.broker.paper import PaperBroker

        if not isinstance(self.broker, PaperBroker):
            raise TypeError("run_until_end requires PaperBroker")
        taken: list[Signal] = []
        while True:
            signal = self.on_bar()
            if signal is not None:
                taken.append(signal)
            if not self.broker.step():
                break
        return taken

    def _scan(self) -> Signal | None:
        cfg = self.config
        h1 = self.broker.candles(cfg.symbol, cfg.bias_tf, cfg.lookback_bars)
        m15 = self.broker.candles(cfg.symbol, cfg.structure_tf, cfg.lookback_bars)
        m5 = self.broker.candles(cfg.symbol, cfg.entry_tf, cfg.lookback_bars)
        evaluation = self.strategy.diagnose(h1, m15, m5)
        self.last_evaluation = evaluation
        return evaluation.signal

    def _enter(self, signal: Signal) -> Position:
        volume = lot_size(self.broker.balance(), self.config)
        if volume <= 0:
            raise RuntimeError("Lot size is 0; deposit funds before trading")
        position = self.broker.open_trade(
            symbol=self.config.symbol,
            side=signal.side,
            volume=volume,
            sl=signal.sl,
            tp=signal.tp,
            comment=self.config.comment,
            magic=self.config.magic,
        )
        self.initial_stops[position.ticket] = position.sl
        self.trades_today += 1
        self.signals.append(signal)
        logger.info(
            "Opened %s %.2f lots @ %.2f SL %.2f TP %.2f RR %.2f (%s)",
            signal.side,
            volume,
            position.entry,
            signal.sl,
            signal.tp,
            signal.rr,
            ", ".join(signal.reasons),
        )
        return position

    def _manage_open_trade(self) -> None:
        positions = self.broker.open_positions(self.config.magic)
        if not positions:
            return
        bid, ask = self.broker.bid_ask(self.config.symbol)
        for position in positions:
            if position.ticket in self.initial_stops:
                position.initial_sl = self.initial_stops[position.ticket]
            price = bid if position.side == "buy" else ask
            new_sl = breakeven_stop(position, price, self.config)
            if position.side == "buy" and new_sl > position.sl:
                self.broker.modify_sl(position.ticket, new_sl)
                logger.info("Moved buy SL to breakeven at %.2f", new_sl)
            elif position.side == "sell" and new_sl < position.sl:
                self.broker.modify_sl(position.ticket, new_sl)
                logger.info("Moved sell SL to breakeven at %.2f", new_sl)

    def _roll_day(self) -> None:
        today = date.today()
        if self._today != today:
            self._today = today
            self.trades_today = 0

    def _bar_time(self) -> datetime | None:
        try:
            m5 = self.broker.candles(self.config.symbol, self.config.entry_tf, 1)
        except Exception:  # pragma: no cover - live feed errors are logged by caller
            return datetime.now(timezone.utc)
        if m5.empty:
            return datetime.now(timezone.utc)
        value = m5.iloc[-1]["time"]
        if isinstance(value, datetime):
            return value
        return None
