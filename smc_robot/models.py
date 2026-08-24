from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Timeframe(str, Enum):
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Trend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGING = "RANGING"


class EventType(str, Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"
    MSS = "MSS"


class SwingKind(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class Candle(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: float = 0.0

    @property
    def bullish(self) -> bool:
        return self.close >= self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2.0


class Swing(BaseModel):
    kind: SwingKind
    index: int
    time: datetime
    price: float


class StructureEvent(BaseModel):
    event_type: EventType
    direction: Direction
    index: int
    time: datetime
    level: float
    close: float


class ZoneKind(str, Enum):
    ORDER_BLOCK = "ORDER_BLOCK"
    FVG = "FVG"
    LIQUIDITY = "LIQUIDITY"


class Zone(BaseModel):
    kind: ZoneKind
    direction: Direction
    index: int
    time: datetime
    low: float
    high: float
    extra: dict = Field(default_factory=dict)

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2.0

    def overlaps(self, low: float, high: float) -> bool:
        return low <= self.high and high >= self.low

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


class LiquiditySweep(BaseModel):
    direction: Direction
    index: int
    time: datetime
    swept_price: float
    wick: float
    close: float
    equal_liquidity: bool = False


class MarketConditions(BaseModel):
    atr: float
    atr_ratio: float
    efficiency: float
    spread: float
    spread_ratio: float
    choppy: bool
    extreme_volatility: bool
    poor: bool
    reasons: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    total: float
    rule_score: float
    ml_score: Optional[float] = None
    components: dict[str, float] = Field(default_factory=dict)
    features: dict[str, float] = Field(default_factory=dict)


class TradePlan(BaseModel):
    direction: Direction
    entry: float
    sl: float
    tp: float
    risk: float
    lots: float
    sl_source: str

    @property
    def one_r(self) -> float:
        return self.risk


class Signal(BaseModel):
    direction: Direction
    plan: TradePlan
    score: ScoreBreakdown
    sweep: Optional[LiquiditySweep] = None
    order_block: Optional[Zone] = None
    fvg: Optional[Zone] = None
    h1_trend: Trend
    m30_trend: Trend
    m15_trend: Trend
    reason: str


class Decision(BaseModel):
    action: str
    reason: str
    score: Optional[ScoreBreakdown] = None
    signal: Optional[Signal] = None


class Position(BaseModel):
    ticket: int
    symbol: str
    direction: Direction
    volume: float
    entry: float
    sl: float
    tp: float
    initial_sl: float
    initial_risk: float
    breakeven_applied: bool = False
    magic: int = 0
    comment: str = ""
