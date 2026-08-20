from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from smc_robot.broker.base import Broker
from smc_robot.config import Position, Side
from smc_robot.smc.candles import MultiTimeframeBars, ensure_ohlc


class PaperBroker(Broker):
    """In-memory broker for tests, demos, and backtests."""

    def __init__(self, m5: pd.DataFrame, starting_balance: float = 1000.0, index: int | None = None) -> None:
        self._m5 = ensure_ohlc(m5)
        self._mtf = MultiTimeframeBars.from_m5(self._m5)
        self._balance = float(starting_balance)
        self._index = len(self._m5) - 1 if index is None else index
        self._positions: dict[int, Position] = {}
        self._next_ticket = 1
        self._connected = False
        self.closed: list[Position] = []

    def connect(self) -> None:
        self._connected = True

    def shutdown(self) -> None:
        self._connected = False

    def set_index(self, index: int) -> None:
        self._index = max(0, min(index, len(self._m5) - 1))
        self._close_touched()

    def step(self) -> bool:
        if self._index >= len(self._m5) - 1:
            return False
        self._index += 1
        self._close_touched()
        return True

    def current_bar(self) -> pd.Series:
        return self._m5.iloc[self._index]

    def balance(self) -> float:
        return self._balance

    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        del symbol
        m5_slice = self._m5.iloc[: self._index + 1]
        mtf = MultiTimeframeBars.from_m5(m5_slice)
        frame = {"M5": mtf.m5, "M15": mtf.m15, "H1": mtf.h1}[timeframe]
        return frame.tail(count).reset_index(drop=True)

    def open_positions(self, magic: int | None = None) -> list[Position]:
        positions = [p for p in self._positions.values() if not p.closed]
        if magic is None:
            return positions
        return [p for p in positions if p.magic == magic]

    def open_trade(
        self,
        symbol: str,
        side: Side,
        volume: float,
        sl: float,
        tp: float,
        comment: str,
        magic: int,
    ) -> Position:
        del symbol
        if self.open_positions(magic):
            raise RuntimeError("Robot already has an open position")
        bar = self.current_bar()
        entry = float(bar["close"])
        position = Position(
            ticket=self._next_ticket,
            side=side,
            volume=volume,
            entry=entry,
            sl=sl,
            tp=tp,
            initial_sl=sl,
            opened_at=bar["time"],
            comment=comment,
            magic=magic,
        )
        self._positions[position.ticket] = position
        self._next_ticket += 1
        return position

    def modify_sl(self, ticket: int, sl: float) -> None:
        self._positions[ticket].sl = sl

    def bid_ask(self, symbol: str) -> tuple[float, float]:
        del symbol
        price = float(self.current_bar()["close"])
        return price, price

    def _close_touched(self) -> None:
        bar = self.current_bar()
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        for position in list(self._positions.values()):
            if position.closed:
                continue
            hit = None
            exit_price = close
            if position.side == "buy":
                if low <= position.sl:
                    hit = "sl"
                    exit_price = position.sl
                elif high >= position.tp:
                    hit = "tp"
                    exit_price = position.tp
            else:
                if high >= position.sl:
                    hit = "sl"
                    exit_price = position.sl
                elif low <= position.tp:
                    hit = "tp"
                    exit_price = position.tp
            if hit:
                self._realize(position, exit_price, hit)

    def _realize(self, position: Position, price: float, reason: str) -> None:
        if position.side == "buy":
            pnl = (price - position.entry) * position.volume * 100.0
        else:
            pnl = (position.entry - price) * position.volume * 100.0
        self._balance += pnl
        position.closed = True
        position.exit_price = price
        position.close_reason = reason
        self.closed.append(position)
        self._positions.pop(position.ticket, None)

    @staticmethod
    def synthetic_gold(bars: int = 600, seed: int = 7) -> pd.DataFrame:
        """Deterministic XAU-like series with directional legs for paper demos."""
        rng_state = seed
        prices = [2350.0]
        for i in range(bars - 1):
            rng_state = (1103515245 * rng_state + 12345) & 0x7FFFFFFF
            step = ((rng_state % 100) - 48) / 20.0
            if 80 <= i < 160:
                step = -abs(step) - 0.15
            if 200 <= i < 280:
                step = abs(step) + 0.25
            if 360 <= i < 420:
                step = -abs(step) - 0.1
            if 460 <= i < 540:
                step = abs(step) + 0.35
            prices.append(max(1800.0, prices[-1] + step))

        rows = []
        start = datetime(2026, 1, 2, tzinfo=timezone.utc)
        for i, close in enumerate(prices):
            rng_state = (1103515245 * (seed + i) + 12345) & 0x7FFFFFFF
            wick = 0.4 + (rng_state % 40) / 50.0
            open_ = prices[i - 1] if i else close
            high = max(open_, close) + wick
            low = min(open_, close) - wick * 0.7
            rows.append(
                {
                    "time": start + pd.Timedelta(minutes=5 * i),
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": 100.0,
                }
            )
        return pd.DataFrame(rows)
