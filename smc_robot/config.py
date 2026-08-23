from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Literal


Timeframe = Literal["M5", "M15", "H1"]
Direction = Literal["bullish", "bearish"]
Side = Literal["buy", "sell"]
Impact = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class NewsEvent:
    time: datetime
    title: str = ""
    impact: Impact = "high"


@dataclass(frozen=True)
class RobotConfig:
    """Runtime settings for FredFx v1 SMC."""

    symbol: str = "XAUUSDm"
    timeframes: tuple[Timeframe, ...] = ("H1", "M15", "M5")
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
    news_blackout_minutes: int = 30
    news_block_impacts: tuple[str, ...] = ("high",)
    news_events: tuple[NewsEvent, ...] = ()
    news_calendar_path: str | None = None
    max_trades_per_day: int | None = None
    sl_buffer: float = 0.50
    swing_left: int = 2
    swing_right: int = 2
    recent_event_bars: int = 40
    equal_tolerance: float = 0.80
    require_liquidity_sweep: bool = True
    require_m15_liquidity: bool = True
    require_m15_pd_array: bool = True
    require_m5_structure_after_sweep: bool = True
    breakeven_at_r: float = 1.0
    breakeven_offset: float = 0.0
    magic: int = 26082301
    comment: str = "FredFx v1 SMC"
    robot_name: str = "FredFx v1 SMC"
    poll_seconds: float = 5.0
    lookback_bars: int = 400
    cooldown_bars: int = 8

    def validate(self) -> None:
        if self.risk_reward <= 0:
            raise ValueError("risk_reward must be positive")
        if self.max_open_positions != 1:
            raise ValueError("FredFx v1 SMC holds exactly 1 open position")
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
class LiquidityZone:
    """A pool of resting stops: swing high/low or equal highs/lows."""

    index: int
    time: object
    low: float
    high: float
    direction: Direction
    kind: Literal["swing", "equal"]
    swept: bool = False

    @property
    def side(self) -> str:
        return "sell_side" if self.direction == "bullish" else "buy_side"

    @property
    def price(self) -> float:
        return (self.low + self.high) / 2.0


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


@dataclass(frozen=True)
class Evaluation:
    """Result of one sequential H1 → M15 → M5 scan."""

    signal: Signal | None
    blocked_by: str | None = None
    stages: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.signal is not None


def load_config(path: str | Path | None = None, **overrides) -> RobotConfig:
    """Build a config from defaults, optional YAML, then keyword overrides."""
    data: dict = {}
    if path is not None:
        data.update(_read_simple_yaml(Path(path)))
    data.update({k: v for k, v in overrides.items() if v is not None})
    if "news_events" in data:
        data["news_events"] = _parse_news_events(data["news_events"])
    if "news_block_impacts" in data and not isinstance(data["news_block_impacts"], tuple):
        data["news_block_impacts"] = tuple(data["news_block_impacts"])
    if "timeframes" in data and not isinstance(data["timeframes"], tuple):
        data["timeframes"] = tuple(data["timeframes"])
    allowed = {f.name for f in fields(RobotConfig)}
    cfg = RobotConfig(**{k: v for k, v in data.items() if k in allowed})
    cfg.validate()
    return cfg


def _parse_news_events(raw) -> tuple[NewsEvent, ...]:
    events: list[NewsEvent] = []
    for item in raw or []:
        if isinstance(item, NewsEvent):
            events.append(item)
            continue
        when = item["time"] if isinstance(item, dict) else item
        if isinstance(when, str):
            when = datetime.fromisoformat(when.replace("Z", "+00:00"))
        title = item.get("title", "") if isinstance(item, dict) else ""
        impact = item.get("impact", "high") if isinstance(item, dict) else "high"
        events.append(NewsEvent(time=when, title=title, impact=impact))
    return tuple(events)


def _read_simple_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}
    except ImportError:
        return _parse_flat_yaml(path.read_text(encoding="utf-8"))


def _parse_flat_yaml(text: str) -> dict:
    """Minimal key: value parser used when PyYAML is not installed."""
    out: dict = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line or line.startswith("-"):
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if not value:
            continue
        out[key] = _coerce_scalar(value)
    return out


def _coerce_scalar(value: str):
    lowered = value.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if lowered in {"null", "none"}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
