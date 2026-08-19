"""In-memory paper broker used for tests, dry-run, and backtests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import pandas as pd

from smc_robot.broker.base import AccountState, Broker, Position
from smc_robot.config import RobotConfig

Side = Literal["buy", "sell"]


class PaperBroker(Broker):
    def __init__(
        self,
        config: RobotConfig | None = None,
        frames: dict[str, pd.DataFrame] | None = None,
        price: float | None = None,
    ) -> None:
        self.config = config or RobotConfig()
        self.symbol = self.config.symbol
        self._frames = frames or {}
        self._balance = self.config.starting_balance
        self._positions: list[Position] = []
        self._next_ticket = 1
        self._now = datetime.now(timezone.utc)
        if price is None and self._frames:
            h1 = self._frames["H1"] if "H1" in self._frames else next(iter(self._frames.values()))
            if len(h1):
                price = float(h1.iloc[-1]["close"])
        self.price = float(price or 2400.0)

    def set_frames(self, frames: dict[str, pd.DataFrame]) -> None:
        self._frames = frames
        if frames:
            h1 = frames["H1"] if "H1" in frames else next(iter(frames.values()))
            if len(h1):
                self.price = float(h1.iloc[-1]["close"])

    def set_price(self, price: float, time: datetime | None = None) -> None:
        self.price = price
        if time:
            self._now = time
        self._mark_to_market()

    def account(self) -> AccountState:
        open_pnl = sum(self._unrealized(p) for p in self.open_positions)
        return AccountState(
            balance=self._balance,
            equity=self._balance + open_pnl,
            positions=list(self._positions),
        )

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self._positions if not p.closed]

    def candles(self, timeframe: str, count: int = 300) -> pd.DataFrame:
        if timeframe not in self._frames:
            raise KeyError(f"no candles loaded for {timeframe}")
        return self._frames[timeframe].iloc[-count:].reset_index(drop=True)

    def bid_ask(self) -> tuple[float, float]:
        half = self.config.spread / 2.0
        return self.price - half, self.price + half

    def open_trade(
        self,
        side: Side,
        volume: float,
        sl: float,
        tp: float,
        timeframe: str,
        comment: str = "",
    ) -> Position:
        bid, ask = self.bid_ask()
        entry = ask if side == "buy" else bid
        risk = abs(entry - sl)
        pos = Position(
            ticket=self._next_ticket,
            symbol=self.symbol,
            side=side,
            volume=volume,
            entry=entry,
            sl=sl,
            tp=tp,
            timeframe=timeframe,
            opened_at=self._now,
            original_sl=sl,
            original_risk=risk,
            comment=comment,
        )
        self._next_ticket += 1
        self._positions.append(pos)
        return pos

    def modify_sl(self, ticket: int, sl: float) -> None:
        pos = self._get(ticket)
        if pos.side == "buy":
            pos.sl = max(pos.sl, sl)
        else:
            pos.sl = min(pos.sl, sl)

    def close_trade(self, ticket: int, reason: str = "manual") -> Position:
        pos = self._get(ticket)
        bid, ask = self.bid_ask()
        exit_price = bid if pos.side == "buy" else ask
        return self._close(pos, exit_price, reason)

    def _get(self, ticket: int) -> Position:
        for pos in self._positions:
            if pos.ticket == ticket and not pos.closed:
                return pos
        raise KeyError(f"open ticket {ticket} not found")

    def _unrealized(self, pos: Position) -> float:
        bid, ask = self.bid_ask()
        price = bid if pos.side == "buy" else ask
        return self._pnl(pos, price)

    def _pnl(self, pos: Position, exit_price: float) -> float:
        direction = 1.0 if pos.side == "buy" else -1.0
        return (exit_price - pos.entry) * direction * pos.volume * self.config.contract_size

    def _close(self, pos: Position, exit_price: float, reason: str) -> Position:
        pos.closed = True
        pos.exit_price = exit_price
        pos.exit_reason = reason
        pos.profit = self._pnl(pos, exit_price)
        self._balance += pos.profit
        return pos

    def _mark_to_market(self) -> None:
        for pos in list(self.open_positions):
            if pos.side == "buy":
                if self.price <= pos.sl:
                    self._close(pos, pos.sl, "sl")
                elif self.price >= pos.tp:
                    self._close(pos, pos.tp, "tp")
            else:
                if self.price >= pos.sl:
                    self._close(pos, pos.sl, "sl")
                elif self.price <= pos.tp:
                    self._close(pos, pos.tp, "tp")
