from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Timeframe = Literal["M5", "M15", "H1"]
Direction = Literal["bullish", "bearish"]
Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class RobotConfig:
    """Runtime settings for the XAUUSDm SMC robot."""

    symbol: str = "XAUUSDm"
    timeframes: tuple[Timeframe, ...] = ("M5", "M15", "H1")
    bias_tf: Timeframe = "H1"
    structure_tf: Timeframe = "M15"
    entry_tf: Timeframe = "M5"
    risk_reward: float = 2.0
    lot_per_100: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 10.0
    lot_step: float = 0.01
    max_open_positions: int = 1
    trade_news: bool = True
    max_trades_per_day: int | None = None
    sl_buffer: float = 0.50
    swing_left: int = 2
    swing_right: int = 2
    min_confluence: int = 4
    recent_event_bars: int = 40
    require_liquidity_sweep: bool = True
    breakeven_at_r: float = 1.0
    breakeven_offset: float = 0.0
    magic: int = 26082026
    comment: str = "XAUUSDm SMC"
    robot_name: str = "XAUUSDm SMC Robot"
    poll_seconds: float = 5.0
    lookback_bars: int = 400
    cooldown_bars: int = 8

    def validate(self) -> None:
        if self.risk_reward <= 0:
            raise ValueError("risk_reward must be positive")
        if self.max_open_positions != 1:
            raise ValueError("This robot is designed to hold exactly 1 position")
        if self.lot_per_100 <= 0:
            raise ValueError("lot_per_100 must be positive")
        missing = {self.bias_tf, self.structure_tf, self.entry_tf} - set(self.timeframes)
        if missing:
            raise ValueError(f"timeframes must include {sorted(missing)}")


@dataclass(frozen=True)
class Candle:
    time: object
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Swing:
    index: int
    time: object
    price: float
    kind: Literal["high", "low"]


@dataclass(frozen=True)
class StructureEvent:
    index: int
    time: object
    kind: Literal["BOS", "CHOCH", "MSS"]
    direction: Direction
    broken_price: float
    close: float


@dataclass(frozen=True)
class LiquiditySweep:
    index: int
    time: object
    direction: Direction
    swept_price: float
    wick: float
    close: float

    @property
    def kind(self) -> str:
        return "sell_side" if self.direction == "bullish" else "buy_side"


@dataclass(frozen=True)
class Zone:
    start_index: int
    end_index: int
    time: object
    low: float
    high: float
    direction: Direction
    kind: Literal["OB", "FVG"]
    mitigated: bool = False

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass(frozen=True)
class Signal:
    side: Side
    entry: float
    sl: float
    tp: float
    confluence: int
    reasons: tuple[str, ...] = field(default_factory=tuple)
    zone_kind: str = ""
    time: object | None = None

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def reward(self) -> float:
        return abs(self.tp - self.entry)

    @property
    def rr(self) -> float:
        return self.reward / self.risk if self.risk else 0.0


@dataclass
class Position:
    ticket: int
    side: Side
    volume: float
    entry: float
    sl: float
    tp: float
    initial_sl: float
    opened_at: object
    comment: str = ""
    magic: int = 0
    closed: bool = False
    exit_price: float | None = None
    close_reason: str = ""

    @property
    def risk(self) -> float:
        return abs(self.entry - self.initial_sl)
