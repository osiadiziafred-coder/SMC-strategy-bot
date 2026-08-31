from __future__ import annotations

from datetime import datetime, timezone

from smc_robot.broker.base import Broker
from smc_robot.models import Candle, Direction, Position
from smc_robot.risk.protection import Quote
from smc_robot.risk.sizing import SymbolSpec


class PaperBroker(Broker):
    """In-memory broker used for tests, dry-run, and replay."""

    def __init__(
        self,
        spec: SymbolSpec | None = None,
        balance: float = 1000.0,
        candles_by_tf: dict[str, list[Candle]] | None = None,
        bid: float = 2000.0,
        ask: float = 2000.25,
        quote_time: datetime | None = None,
    ):
        self.spec = spec or SymbolSpec(
            name="XAUUSDm",
            bid=bid,
            ask=ask,
            spread=(ask - bid) / 0.01 if ask >= bid else 0.0,
            trade_mode="full",
        )
        self.balance = balance
        self.candles_by_tf = candles_by_tf or {}
        self.bid = bid
        self.ask = ask
        self.quote_time = quote_time or datetime.now(timezone.utc)
        self.positions: list[Position] = []
        self._next_ticket = 1
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def shutdown(self) -> None:
        self.connected = False

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        if symbol != self.spec.name:
            raise RuntimeError(f"Exact symbol {symbol} not found (paper has {self.spec.name})")
        return SymbolSpec(
            name=self.spec.name,
            point=self.spec.point,
            digits=self.spec.digits,
            volume_min=self.spec.volume_min,
            volume_max=self.spec.volume_max,
            volume_step=self.spec.volume_step,
            trade_stops_level=self.spec.trade_stops_level,
            filling_mode=self.spec.filling_mode,
            tick_size=self.spec.tick_size,
            tick_value=self.spec.tick_value,
            margin_initial=self.spec.margin_initial,
            trade_mode=self.spec.trade_mode,
            spread=(self.ask - self.bid) / self.spec.point if self.spec.point else self.spec.spread,
            bid=self.bid,
            ask=self.ask,
        )

    def account_balance(self) -> float:
        return self.balance

    def candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        series = self.candles_by_tf.get(timeframe, [])
        return series[-count:]

    def quote(self, symbol: str) -> Quote:
        spread = (self.ask - self.bid) / self.spec.point if self.spec.point else 0.0
        return Quote(bid=self.bid, ask=self.ask, time=self.quote_time, spread_points=spread)

    def set_quote(self, bid: float, ask: float, time: datetime | None = None) -> None:
        self.bid = bid
        self.ask = ask
        if time is not None:
            self.quote_time = time

    def set_candles(self, timeframe: str, candles: list[Candle]) -> None:
        self.candles_by_tf[timeframe] = candles

    def open_positions(self, symbol: str, magic: int) -> list[Position]:
        return [p for p in self.positions if p.symbol == symbol and p.magic == magic]

    def market_order(
        self,
        symbol: str,
        direction: Direction,
        lots: float,
        sl: float,
        tp: float,
        deviation_points: int,
        magic: int,
        comment: str,
    ) -> Position:
        price = self.ask if direction == Direction.BUY else self.bid
        position = Position(
            ticket=self._next_ticket,
            symbol=symbol,
            direction=direction,
            volume=lots,
            entry=price,
            sl=sl,
            tp=tp,
            initial_sl=sl,
            initial_risk=abs(price - sl),
            magic=magic,
            comment=comment,
        )
        self._next_ticket += 1
        self.positions.append(position)
        return position

    def modify_sl(self, position: Position, sl: float) -> Position:
        updated = position.model_copy(update={"sl": sl})
        self.positions = [updated if p.ticket == position.ticket else p for p in self.positions]
        return updated

    def close_all(self) -> None:
        self.positions = []
