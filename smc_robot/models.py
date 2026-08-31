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


class SetupGrade(str, Enum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"


class SessionName(str, Enum):
    ASIAN = "ASIAN"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP = "LONDON_NY_OVERLAP"
    OFF = "OFF"


class NewsMode(str, Enum):
    ALLOW = "allow"
    AVOID_HIGH = "avoid_high"
    WINDOW = "window"
    AFTER_ONLY = "after_only"


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

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


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
    members: int = 1
    rejection_ratio: float = 0.0
    pool_scope: str = "internal"
    extra: dict = Field(default_factory=dict)


class Displacement(BaseModel):
    body_atr: float = 0.0
    wick_body_ratio: float = 0.0
    consecutive: int = 0
    strong: bool = False


class PremiumDiscount(BaseModel):
    range_low: float = 0.0
    range_high: float = 0.0
    position: float = 0.5
    in_discount: bool = False
    in_premium: bool = False


class MarketConditions(BaseModel):
    atr: float
    atr_ratio: float
    efficiency: float
    spread: float
    spread_ratio: float
    choppy: bool
    extreme_volatility: bool
    low_volatility: bool = False
    high_volatility: bool = False
    poor: bool
    reasons: list[str] = Field(default_factory=list)
    session: SessionName = SessionName.OFF
    displacement: Displacement = Field(default_factory=Displacement)
    premium_discount: PremiumDiscount = Field(default_factory=PremiumDiscount)


class ScoreBreakdown(BaseModel):
    total: float
    rule_score: float
    ml_score: Optional[float] = None
    ml_probability: Optional[float] = None
    ml_buy_probability: Optional[float] = None
    ml_sell_probability: Optional[float] = None
    grade: SetupGrade = SetupGrade.C
    components: dict[str, float] = Field(default_factory=dict)
    features: dict[str, float] = Field(default_factory=dict)
    explanation: list[dict] = Field(default_factory=list)


class TradePlan(BaseModel):
    direction: Direction
    entry: float
    sl: float
    tp: float
    risk: float
    lots: float
    sl_source: str
    risk_amount: float = 0.0
    tp_adjusted: bool = False

    @property
    def one_r(self) -> float:
        return self.risk


class Signal(BaseModel):
    signal_id: str
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
    grade: SetupGrade = SetupGrade.C


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
    trailing_applied: bool = False
    magic: int = 0
    comment: str = ""
    signal_id: str = ""


class DecisionRecord(BaseModel):
    time: datetime
    symbol: str
    action: str
    reason: str
    direction: Optional[str] = None
    h1_trend: Optional[str] = None
    m30_trend: Optional[str] = None
    m15_trend: Optional[str] = None
    bos: bool = False
    mss: bool = False
    choch: bool = False
    liquidity_sweep: bool = False
    equal_liquidity: bool = False
    order_block: bool = False
    fvg: bool = False
    atr: float = 0.0
    spread: float = 0.0
    session: Optional[str] = None
    ml_probability: Optional[float] = None
    rule_score: Optional[float] = None
    final_score: Optional[float] = None
    grade: Optional[str] = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    lots: Optional[float] = None
    signal_id: Optional[str] = None
    result: Optional[str] = None
    rejection_reason: Optional[str] = None
    profit_loss: Optional[float] = None
    r_multiple: Optional[float] = None
    mfe: Optional[float] = None
    mae: Optional[float] = None
    fill_price: Optional[float] = None
    ml_buy_probability: Optional[float] = None
    ml_sell_probability: Optional[float] = None
    explanation: list[dict] = Field(default_factory=list)
    summary: Optional[str] = None
    features: dict[str, float] = Field(default_factory=dict)
