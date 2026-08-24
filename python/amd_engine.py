"""Session-based Accumulation / Manipulation / Distribution engine.

This module is a rules-faithful port of the MT5 EA decision core so the
strategy can be unit-tested without MetaTrader. It does not place live
orders; it emits structured signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable, List, Optional, Sequence, Tuple


class Phase(str, Enum):
    IDLE = "IDLE"
    ACCUMULATION = "ACCUMULATION"
    RANGE_SET = "RANGE_SET"
    MANIPULATION = "MANIPULATION"
    CONFIRMATION = "CONFIRMATION"
    IN_TRADE = "IN_TRADE"
    CYCLE_COMPLETE = "CYCLE_COMPLETE"
    RANGE_INVALID = "RANGE_INVALID"


class Direction(str, Enum):
    NONE = "NONE"
    BUY = "BUY"
    SELL = "SELL"


class SweepReturnMode(str, Enum):
    INSIDE_RANGE = "INSIDE_RANGE"
    THROUGH_LEVEL = "THROUGH_LEVEL"
    WICK_ONLY = "WICK_ONLY"


class ConfirmMode(str, Enum):
    BOS = "BOS"
    CISD = "CISD"
    BOS_AND_CISD = "BOS_AND_CISD"


class EntryMode(str, Enum):
    MARKET = "MARKET"
    RETEST = "RETEST"
    FVG = "FVG"


class TpMode(str, Enum):
    RISK_REWARD = "RISK_REWARD"
    LIQUIDITY = "LIQUIDITY"
    HYBRID = "HYBRID"


class HtfBiasMode(str, Enum):
    OFF = "OFF"
    WITH_TREND = "WITH_TREND"
    COUNTER_TREND = "COUNTER_TREND"


class SessionKind(str, Enum):
    NONE = "NONE"
    ASIA = "ASIA"
    LONDON = "LONDON"
    NEWYORK = "NEWYORK"


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class SessionWindow:
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int

    @property
    def start_min(self) -> int:
        return self.start_hour * 60 + self.start_minute

    @property
    def end_min(self) -> int:
        return self.end_hour * 60 + self.end_minute


@dataclass
class AMDConfig:
    asia: SessionWindow = field(default_factory=lambda: SessionWindow(0, 0, 8, 0))
    london: SessionWindow = field(default_factory=lambda: SessionWindow(8, 0, 12, 0))
    newyork: SessionWindow = field(default_factory=lambda: SessionWindow(12, 0, 17, 0))
    trade_london: bool = True
    trade_newyork: bool = True
    point: float = 0.0001
    min_range_points: float = 50.0
    max_range_points: float = 800.0
    min_acc_bars: int = 4
    min_sweep_points: float = 5.0
    sweep_buffer_points: float = 0.0
    sweep_return: SweepReturnMode = SweepReturnMode.INSIDE_RANGE
    swing_strength: int = 2
    confirm_mode: ConfirmMode = ConfirmMode.BOS
    require_rejection: bool = True
    require_displacement: bool = False
    displacement_atr_mult: float = 0.8
    entry_mode: EntryMode = EntryMode.MARKET
    max_bars_after_mss: int = 12
    retest_max_bars: int = 8
    sl_buffer_points: float = 30.0
    max_sl_points: float = 400.0
    min_sl_points: float = 40.0
    risk_reward: float = 2.0
    tp_mode: TpMode = TpMode.HYBRID
    max_spread_points: float = 35.0
    max_atr_points: float = 0.0
    min_atr_points: float = 0.0
    skip_high_volatility: bool = True
    volatility_atr_mult: float = 2.5
    max_trades_per_day: int = 1
    one_trade_per_cycle: bool = True
    allow_buy: bool = True
    allow_sell: bool = True
    htf_bias_mode: HtfBiasMode = HtfBiasMode.OFF
    equal_tolerance_points: float = 20.0


@dataclass
class SessionRange:
    t_start: datetime
    t_end: datetime
    open: float
    high: float
    low: float
    close: float
    complete: bool
    valid: bool
    name: str = "ASIA"

    @property
    def range_size(self) -> float:
        return self.high - self.low

    @property
    def range_points(self) -> float:
        return self.range_size


@dataclass
class SweepEvent:
    active: bool = False
    setup_dir: Direction = Direction.NONE
    level: float = 0.0
    extreme: float = 0.0
    t_sweep: Optional[datetime] = None
    sweep_open: float = 0.0
    sweep_close: float = 0.0
    sweep_high: float = 0.0
    sweep_low: float = 0.0
    returned: bool = False
    t_returned: Optional[datetime] = None


@dataclass
class StructureShift:
    confirmed: bool = False
    direction: Direction = Direction.NONE
    t_shift: Optional[datetime] = None
    broken_level: float = 0.0
    fvg_top: float = 0.0
    fvg_bottom: float = 0.0
    has_fvg: bool = False
    entry_zone_high: float = 0.0
    entry_zone_low: float = 0.0


@dataclass
class Signal:
    direction: Direction
    time: datetime
    entry: float
    sl: float
    tp: float
    liquidity_target: float
    reason: str
    phase: Phase


@dataclass
class LiquidityLevel:
    price: float
    buy_side: bool
    label: str
    time: datetime


def minutes_of(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def in_window(dt: datetime, window: SessionWindow) -> bool:
    now = minutes_of(dt)
    start, end = window.start_min, window.end_min
    if start == end:
        return True
    if start < end:
        return start <= now < end
    return now >= start or now < end


def date_floor(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def session_bounds(now: datetime, window: SessionWindow) -> Tuple[datetime, datetime]:
    start, end = window.start_min, window.end_min
    day = date_floor(now)
    now_min = minutes_of(now)

    if start == end:
        return day, day + timedelta(days=1)

    if start < end:
        today_start = day + timedelta(minutes=start)
        today_end = day + timedelta(minutes=end)
        if now_min >= start:
            return today_start, today_end
        return today_start - timedelta(days=1), today_end - timedelta(days=1)

    if now_min >= start:
        return day + timedelta(minutes=start), day + timedelta(days=1, minutes=end)
    return day - timedelta(days=1) + timedelta(minutes=start), day + timedelta(minutes=end)


def current_session(now: datetime, cfg: AMDConfig) -> SessionKind:
    if in_window(now, cfg.asia):
        return SessionKind.ASIA
    if in_window(now, cfg.london):
        return SessionKind.LONDON
    if in_window(now, cfg.newyork):
        return SessionKind.NEWYORK
    return SessionKind.NONE


def in_trade_window(now: datetime, cfg: AMDConfig) -> bool:
    kind = current_session(now, cfg)
    if kind == SessionKind.LONDON:
        return cfg.trade_london
    if kind == SessionKind.NEWYORK:
        return cfg.trade_newyork
    return False


def points(cfg: AMDConfig, price_dist: float) -> float:
    if cfg.point <= 0:
        return 0.0
    return price_dist / cfg.point


def price_from_points(cfg: AMDConfig, pts: float) -> float:
    return pts * cfg.point


def is_swing_high(candles: Sequence[Candle], i: int, strength: int) -> bool:
    """i is index in chronological list (0 = oldest)."""
    if i < strength or i + strength >= len(candles):
        return False
    high = candles[i].high
    for k in range(1, strength + 1):
        if high <= candles[i - k].high or high <= candles[i + k].high:
            return False
    return True


def is_swing_low(candles: Sequence[Candle], i: int, strength: int) -> bool:
    if i < strength or i + strength >= len(candles):
        return False
    low = candles[i].low
    for k in range(1, strength + 1):
        if low >= candles[i - k].low or low >= candles[i + k].low:
            return False
    return True


def latest_swing_high(candles: Sequence[Candle], strength: int, end_inclusive: int) -> Optional[int]:
    start = strength
    stop = min(end_inclusive, len(candles) - strength - 1)
    best = None
    for i in range(start, stop + 1):
        if is_swing_high(candles, i, strength):
            best = i
    return best


def latest_swing_low(candles: Sequence[Candle], strength: int, end_inclusive: int) -> Optional[int]:
    start = strength
    stop = min(end_inclusive, len(candles) - strength - 1)
    best = None
    for i in range(start, stop + 1):
        if is_swing_low(candles, i, strength):
            best = i
    return best


def detect_fvg(candles: Sequence[Candle], mid: int, bullish: bool) -> Optional[Tuple[float, float]]:
    if mid < 1 or mid + 1 >= len(candles):
        return None
    older, newer = candles[mid - 1], candles[mid + 1]
    if bullish and newer.low > older.high:
        bottom, top = older.high, newer.low
        return (top, bottom) if top > bottom else None
    if (not bullish) and newer.high < older.low:
        top, bottom = older.low, newer.high
        return (top, bottom) if top > bottom else None
    return None


def equal_levels(prices: Sequence[float], tolerance: float) -> List[float]:
    found: List[float] = []
    for i, a in enumerate(prices):
        for b in prices[i + 1 :]:
            if abs(a - b) <= tolerance:
                found.append(0.5 * (a + b))
    return found


def build_range(candles: Sequence[Candle], now: datetime, cfg: AMDConfig) -> Optional[SessionRange]:
    t_start, t_end = session_bounds(now, cfg.asia)
    inside = [c for c in candles if t_start <= c.time < min(now, t_end)]
    if len(inside) < cfg.min_acc_bars:
        return None
    high = max(c.high for c in inside)
    low = min(c.low for c in inside)
    rng = SessionRange(
        t_start=t_start,
        t_end=t_end,
        open=inside[0].open,
        high=high,
        low=low,
        close=inside[-1].close,
        complete=now >= t_end,
        valid=False,
    )
    pts = points(cfg, rng.range_size)
    rng.valid = pts >= cfg.min_range_points
    if cfg.max_range_points > 0 and pts > cfg.max_range_points:
        rng.valid = False
    return rng


def sweep_returned(bar: Candle, rng: SessionRange, swept_high: bool, mode: SweepReturnMode) -> bool:
    if mode == SweepReturnMode.WICK_ONLY:
        if swept_high:
            return bar.close < bar.high and bar.close <= rng.high
        return bar.close > bar.low and bar.close >= rng.low
    if mode == SweepReturnMode.THROUGH_LEVEL:
        if swept_high:
            return bar.close < rng.high
        return bar.close > rng.low
    if swept_high:
        return rng.low <= bar.close <= rng.high
    return rng.low <= bar.close <= rng.high


def detect_sweep(bar: Candle, rng: SessionRange, cfg: AMDConfig) -> Optional[SweepEvent]:
    if rng is None or not rng.valid:
        return None
    buffer = price_from_points(cfg, cfg.sweep_buffer_points)
    min_run = price_from_points(cfg, cfg.min_sweep_points)

    if bar.high > rng.high + buffer and (bar.high - rng.high) >= min_run:
        ev = SweepEvent(
            active=True,
            setup_dir=Direction.SELL,
            level=rng.high,
            extreme=bar.high,
            t_sweep=bar.time,
            sweep_open=bar.open,
            sweep_close=bar.close,
            sweep_high=bar.high,
            sweep_low=bar.low,
        )
        ev.returned = sweep_returned(bar, rng, True, cfg.sweep_return)
        ev.t_returned = bar.time if ev.returned else None
        return ev

    if bar.low < rng.low - buffer and (rng.low - bar.low) >= min_run:
        ev = SweepEvent(
            active=True,
            setup_dir=Direction.BUY,
            level=rng.low,
            extreme=bar.low,
            t_sweep=bar.time,
            sweep_open=bar.open,
            sweep_close=bar.close,
            sweep_high=bar.high,
            sweep_low=bar.low,
        )
        ev.returned = sweep_returned(bar, rng, False, cfg.sweep_return)
        ev.t_returned = bar.time if ev.returned else None
        return ev
    return None


def confirm_shift(
    candles: Sequence[Candle],
    sweep: SweepEvent,
    cfg: AMDConfig,
    atr: float = 0.0,
) -> Optional[StructureShift]:
    if not sweep.active or not sweep.returned:
        return None

    times = [c.time for c in candles]
    try:
        sweep_idx = times.index(sweep.t_sweep)
    except ValueError:
        return None

    strength = max(cfg.swing_strength, 1)
    sell = sweep.setup_dir == Direction.SELL
    cisd = False
    bos = False
    broken = 0.0
    bos_idx = None

    for i in range(sweep_idx + 1, len(candles)):
        bar = candles[i]
        if sell and bar.close < sweep.sweep_open and bar.close < sweep.sweep_low:
            cisd = True
        if (not sell) and bar.close > sweep.sweep_open and bar.close > sweep.sweep_high:
            cisd = True

    if sell:
        sl = latest_swing_low(candles[: sweep_idx + 1], strength, sweep_idx)
        broken = candles[sl].low if sl is not None else sweep.sweep_low
        for i in range(sweep_idx + 1, len(candles)):
            if candles[i].close < broken:
                bos = True
                bos_idx = i
                break
    else:
        sh = latest_swing_high(candles[: sweep_idx + 1], strength, sweep_idx)
        broken = candles[sh].high if sh is not None else sweep.sweep_high
        for i in range(sweep_idx + 1, len(candles)):
            if candles[i].close > broken:
                bos = True
                bos_idx = i
                break

    if cfg.confirm_mode == ConfirmMode.BOS:
        ok = bos
    elif cfg.confirm_mode == ConfirmMode.CISD:
        ok = cisd
    else:
        ok = bos and cisd
    if not ok:
        return None

    confirm_idx = bos_idx if bos_idx is not None else len(candles) - 1
    body = abs(candles[confirm_idx].close - candles[confirm_idx].open)
    if cfg.require_displacement and atr > 0 and body < atr * cfg.displacement_atr_mult:
        return None

    if cfg.require_rejection:
        after = candles[sweep_idx + 1 : confirm_idx + 1]
        if sell:
            if after and max(c.high for c in after) >= sweep.extreme and not any(
                is_swing_high(candles, sweep_idx + 1 + j, strength) and c.high < sweep.extreme
                for j, c in enumerate(after)
            ):
                # still allow if we already closed back and broke structure
                if max(c.high for c in after) > sweep.extreme:
                    return None
        else:
            if after and min(c.low for c in after) <= sweep.extreme and not any(
                is_swing_low(candles, sweep_idx + 1 + j, strength) and c.low > sweep.extreme
                for j, c in enumerate(after)
            ):
                if min(c.low for c in after) < sweep.extreme:
                    return None

    mss = StructureShift(
        confirmed=True,
        direction=sweep.setup_dir,
        t_shift=candles[confirm_idx].time,
        broken_level=broken,
    )
    fvg = detect_fvg(candles, confirm_idx, bullish=not sell)
    if fvg:
        mss.has_fvg = True
        mss.fvg_top, mss.fvg_bottom = fvg
        mss.entry_zone_high, mss.entry_zone_low = fvg
    else:
        zone = price_from_points(cfg, cfg.sweep_buffer_points + 5)
        if sell:
            mss.entry_zone_high = broken + zone
            mss.entry_zone_low = broken
        else:
            mss.entry_zone_high = broken
            mss.entry_zone_low = broken - zone
    return mss


def htf_bias(candles: Sequence[Candle], strength: int = 2) -> Direction:
    if len(candles) < strength * 4 + 5:
        return Direction.NONE
    for i in range(len(candles) - strength - 1, strength, -1):
        sh = latest_swing_high(candles[:i], strength, i - 1)
        sl = latest_swing_low(candles[:i], strength, i - 1)
        if sh is not None and candles[i].close > candles[sh].high:
            return Direction.BUY
        if sl is not None and candles[i].close < candles[sl].low:
            return Direction.SELL
    return Direction.NONE


def direction_allowed(setup: Direction, bias: Direction, mode: HtfBiasMode) -> bool:
    if mode == HtfBiasMode.OFF or bias == Direction.NONE:
        return True
    if mode == HtfBiasMode.WITH_TREND:
        return setup == bias
    if mode == HtfBiasMode.COUNTER_TREND:
        return setup != bias
    return True


def sl_from_sweep(direction: Direction, sweep: SweepEvent, cfg: AMDConfig) -> float:
    buf = price_from_points(cfg, cfg.sl_buffer_points)
    if direction == Direction.BUY:
        return sweep.extreme - buf
    return sweep.extreme + buf


def tp_from_mode(
    direction: Direction,
    entry: float,
    sl: float,
    liquidity_target: float,
    cfg: AMDConfig,
) -> float:
    sl_dist = abs(entry - sl)
    rr_tp = entry + sl_dist * cfg.risk_reward if direction == Direction.BUY else entry - sl_dist * cfg.risk_reward
    if cfg.tp_mode == TpMode.RISK_REWARD or liquidity_target <= 0:
        return rr_tp
    if cfg.tp_mode == TpMode.LIQUIDITY:
        if direction == Direction.BUY and liquidity_target > entry:
            return liquidity_target
        if direction == Direction.SELL and liquidity_target < entry:
            return liquidity_target
        return rr_tp
    if direction == Direction.BUY:
        return max(rr_tp, liquidity_target)
    return min(rr_tp, liquidity_target)


def validate_stops(direction: Direction, entry: float, sl: float, cfg: AMDConfig) -> Tuple[bool, str]:
    sl_pts = points(cfg, abs(entry - sl))
    if direction == Direction.BUY and sl >= entry:
        return False, "BUY SL must be below entry"
    if direction == Direction.SELL and sl <= entry:
        return False, "SELL SL must be above entry"
    if cfg.min_sl_points > 0 and sl_pts < cfg.min_sl_points:
        return False, "SL too tight"
    if cfg.max_sl_points > 0 and sl_pts > cfg.max_sl_points:
        return False, "SL distance exceeds maximum allowed risk"
    return True, ""


def liquidity_target(direction: Direction, entry: float, rng: SessionRange) -> float:
    if direction == Direction.BUY:
        return rng.high if rng.high > entry else rng.high
    return rng.low


def collect_liquidity(rng: SessionRange, candles: Sequence[Candle], cfg: AMDConfig) -> List[LiquidityLevel]:
    levels = [
        LiquidityLevel(rng.high, True, "Session High BSL", rng.t_end),
        LiquidityLevel(rng.low, False, "Session Low SSL", rng.t_end),
    ]
    strength = cfg.swing_strength
    highs: List[float] = []
    lows: List[float] = []
    for i in range(len(candles)):
        if is_swing_high(candles, i, strength):
            highs.append(candles[i].high)
            levels.append(LiquidityLevel(candles[i].high, True, "Swing High BSL", candles[i].time))
        if is_swing_low(candles, i, strength):
            lows.append(candles[i].low)
            levels.append(LiquidityLevel(candles[i].low, False, "Swing Low SSL", candles[i].time))
    tol = price_from_points(cfg, cfg.equal_tolerance_points)
    for px in equal_levels(highs, tol):
        levels.append(LiquidityLevel(px, True, "Equal Highs BSL", rng.t_end))
    for px in equal_levels(lows, tol):
        levels.append(LiquidityLevel(px, False, "Equal Lows SSL", rng.t_end))
    return levels


class AMDEngine:
    """Stateful AMD processor. Feed chronological LTF candles via process_bar()."""

    def __init__(self, cfg: Optional[AMDConfig] = None):
        self.cfg = cfg or AMDConfig()
        self.phase = Phase.IDLE
        self.range: Optional[SessionRange] = None
        self.sweep = SweepEvent()
        self.mss = StructureShift()
        self.bias = Direction.NONE
        self.cycle_start: Optional[datetime] = None
        self.trades_today = 0
        self.current_day: Optional[datetime] = None
        self.last_skip: str = ""
        self.pending_bars = 0
        self.history: List[Candle] = []

    def reset_cycle(self, start: datetime, why: str) -> None:
        self.phase = Phase.IDLE
        self.range = None
        self.sweep = SweepEvent()
        self.mss = StructureShift()
        self.cycle_start = start
        self.pending_bars = 0
        self.last_skip = why

    def _filters(self, now: datetime, spread_points: float, atr_points: float, atr_avg_points: float) -> Optional[str]:
        cfg = self.cfg
        if cfg.max_spread_points > 0 and spread_points > cfg.max_spread_points:
            return f"Spread too high ({spread_points})"
        if cfg.max_atr_points > 0 and atr_points > cfg.max_atr_points:
            return "ATR too high"
        if cfg.min_atr_points > 0 and atr_points < cfg.min_atr_points:
            return "ATR too low"
        if cfg.skip_high_volatility and atr_avg_points > 0 and atr_points > atr_avg_points * cfg.volatility_atr_mult:
            return "Abnormal volatility"
        if not in_trade_window(now, cfg):
            return "Outside permitted trading session"
        if self.trades_today >= cfg.max_trades_per_day:
            return "Max trades already reached"
        return None

    def process_bar(
        self,
        candle: Candle,
        history: Sequence[Candle],
        spread_points: float = 10.0,
        atr_points: float = 80.0,
        atr_avg_points: float = 70.0,
        htf_candles: Optional[Sequence[Candle]] = None,
    ) -> Optional[Signal]:
        cfg = self.cfg
        now = candle.time
        day = date_floor(now)
        if self.current_day != day:
            self.current_day = day
            self.trades_today = 0

        acc_start, _ = session_bounds(now, cfg.asia)
        if self.cycle_start != acc_start:
            self.reset_cycle(acc_start, "New accumulation session")

        self.history = list(history) + [candle]
        self.range = build_range(self.history, now, cfg)
        session = current_session(now, cfg)
        if htf_candles:
            self.bias = htf_bias(htf_candles, cfg.swing_strength)

        if session == SessionKind.ASIA:
            if self.phase in (Phase.IDLE, Phase.RANGE_INVALID, Phase.RANGE_SET):
                self.phase = Phase.ACCUMULATION
            return None

        if self.range and self.range.valid and self.phase in (Phase.IDLE, Phase.ACCUMULATION):
            self.phase = Phase.RANGE_SET
        elif self.range and (not self.range.valid) and self.range.complete and self.phase in (Phase.IDLE, Phase.ACCUMULATION):
            self.phase = Phase.RANGE_INVALID
            self.last_skip = "Accumulation range rejected by size/bar filters"
            return None

        if self.phase in (Phase.CYCLE_COMPLETE, Phase.RANGE_INVALID, Phase.ACCUMULATION):
            return None
        if self.range is None or not self.range.valid:
            return None

        # Sweep detection — never assumed, only observed.
        # Opposite sweep may replace the working idea ONLY if the first
        # sweep never rejected. Once price has returned inside the range,
        # a later take of the other side is distribution, not a new Judas.
        ev = detect_sweep(candle, self.range, cfg)
        if ev is not None:
            flip = self.sweep.active and ev.setup_dir != self.sweep.setup_dir and not self.sweep.returned
            if (not self.sweep.active) or flip:
                self.sweep = ev
                self.mss = StructureShift()
                self.phase = Phase.MANIPULATION
                self.pending_bars = 0
            elif self.sweep.active:
                if self.sweep.setup_dir == Direction.SELL:
                    self.sweep.extreme = max(self.sweep.extreme, candle.high)
                else:
                    self.sweep.extreme = min(self.sweep.extreme, candle.low)
                if sweep_returned(candle, self.range, self.sweep.setup_dir == Direction.SELL, cfg.sweep_return):
                    self.sweep.returned = True
                    self.sweep.t_returned = candle.time
        elif self.sweep.active:
            if self.sweep.setup_dir == Direction.SELL:
                self.sweep.extreme = max(self.sweep.extreme, candle.high)
            else:
                self.sweep.extreme = min(self.sweep.extreme, candle.low)
            if sweep_returned(candle, self.range, self.sweep.setup_dir == Direction.SELL, cfg.sweep_return):
                self.sweep.returned = True
                self.sweep.t_returned = candle.time

        if self.sweep.active and self.sweep.returned and not self.mss.confirmed:
            mss = confirm_shift(self.history, self.sweep, cfg, atr=atr_points * cfg.point)
            if mss is None:
                self.last_skip = "Sweep returned — waiting for market-structure confirmation"
                return None
            self.mss = mss
            self.phase = Phase.CONFIRMATION

        if not self.mss.confirmed:
            return None

        self.pending_bars += 1
        if cfg.max_bars_after_mss > 0 and self.pending_bars > cfg.max_bars_after_mss:
            self.last_skip = "Confirmation expired"
            self.mss = StructureShift()
            self.pending_bars = 0
            return None

        skip = self._filters(now, spread_points, atr_points, atr_avg_points)
        if skip:
            self.last_skip = skip
            return None
        if self.mss.direction == Direction.BUY and not cfg.allow_buy:
            self.last_skip = "Buys disabled"
            return None
        if self.mss.direction == Direction.SELL and not cfg.allow_sell:
            self.last_skip = "Sells disabled"
            return None
        if not direction_allowed(self.mss.direction, self.bias, cfg.htf_bias_mode):
            self.last_skip = f"HTF bias filter blocked {self.mss.direction.value}"
            return None

        fire = cfg.entry_mode == EntryMode.MARKET
        if cfg.entry_mode in (EntryMode.RETEST, EntryMode.FVG):
            z_hi, z_lo = self.mss.entry_zone_high, self.mss.entry_zone_low
            fire = not (candle.low > z_hi or candle.high < z_lo)
            if not fire and self.pending_bars > cfg.retest_max_bars:
                self.last_skip = "Retest/FVG timeout — setup cancelled"
                self.mss = StructureShift()
                self.sweep = SweepEvent()
                self.phase = Phase.RANGE_SET
                return None
        if not fire:
            return None

        entry = candle.close
        sl = sl_from_sweep(self.mss.direction, self.sweep, cfg)
        ok, reason = validate_stops(self.mss.direction, entry, sl, cfg)
        if not ok:
            self.last_skip = f"Entry skipped: {reason}"
            self.phase = Phase.CYCLE_COMPLETE
            return None

        liq = liquidity_target(self.mss.direction, entry, self.range)
        tp = tp_from_mode(self.mss.direction, entry, sl, liq, cfg)
        signal = Signal(
            direction=self.mss.direction,
            time=now,
            entry=entry,
            sl=sl,
            tp=tp,
            liquidity_target=liq,
            reason="DISTRIBUTION entry after AMD confirmation",
            phase=Phase.IN_TRADE,
        )
        self.trades_today += 1
        self.phase = Phase.CYCLE_COMPLETE if cfg.one_trade_per_cycle else Phase.IN_TRADE
        return signal


def synthesize_amd_sell_day(
    day: datetime,
    start_price: float = 1.10000,
    point: float = 0.0001,
) -> List[Candle]:
    """Build a textbook bearish AMD day: Asia range, London high sweep, MSS, distribution."""
    candles: List[Candle] = []
    t = day.replace(hour=0, minute=0, second=0, microsecond=0)
    px = start_price
    # Asia 00:00-08:00 M5 = 96 bars, chop inside 40-pip range (400 points on 5-digit)
    high_cap = start_price + 120 * point
    low_cap = start_price - 120 * point
    mid = start_price
    for i in range(96):
        o = px
        # Mean-revert inside a tight overnight box
        pull = (mid - px) * 0.25
        noise = (40 * point) if i % 2 == 0 else (-36 * point)
        c = min(max(o + pull + noise, low_cap + 10 * point), high_cap - 10 * point)
        h = min(max(o, c) + 8 * point, high_cap)
        l = max(min(o, c) - 8 * point, low_cap)
        candles.append(Candle(t, o, h, l, c))
        px = c
        t += timedelta(minutes=5)

    # London: rally through Asia high, then reject
    asia_high = max(c.high for c in candles)
    asia_low = min(c.low for c in candles)
    # 4 bars up into the high
    for _ in range(4):
        o = px
        c = o + 50 * point
        candles.append(Candle(t, o, c + 5 * point, o - 5 * point, c))
        px = c
        t += timedelta(minutes=5)
    # Sweep bar
    o = px
    sweep_high = asia_high + 40 * point
    c = asia_high - 30 * point
    candles.append(Candle(t, o, sweep_high, min(o, c) - 10 * point, c))
    px = c
    t += timedelta(minutes=5)
    # Return inside + lower high
    for delta in (-40 * point, -30 * point, -20 * point):
        o = px
        c = o + delta
        candles.append(Candle(t, o, max(o, c) + 10 * point, min(o, c) - 10 * point, c))
        px = c
        t += timedelta(minutes=5)
    # BOS down through a short-term low (and through range mid toward distribution)
    o = px
    c = asia_low + 40 * point
    candles.append(Candle(t, o, o + 5 * point, c - 15 * point, c))
    px = c
    t += timedelta(minutes=5)
    # Distribution continuation
    for _ in range(12):
        o = px
        c = o - 25 * point
        candles.append(Candle(t, o, o + 8 * point, c - 8 * point, c))
        px = c
        t += timedelta(minutes=5)
    return candles


def synthesize_amd_buy_day(
    day: datetime,
    start_price: float = 1.10000,
    point: float = 0.0001,
) -> List[Candle]:
    candles: List[Candle] = []
    t = day.replace(hour=0, minute=0, second=0, microsecond=0)
    px = start_price
    high_cap = start_price + 120 * point
    low_cap = start_price - 120 * point
    mid = start_price
    for i in range(96):
        o = px
        pull = (mid - px) * 0.25
        noise = (-40 * point) if i % 2 == 0 else (36 * point)
        c = min(max(o + pull + noise, low_cap + 10 * point), high_cap - 10 * point)
        h = min(max(o, c) + 8 * point, high_cap)
        l = max(min(o, c) - 8 * point, low_cap)
        candles.append(Candle(t, o, h, l, c))
        px = c
        t += timedelta(minutes=5)

    asia_high = max(c.high for c in candles)
    asia_low = min(c.low for c in candles)
    for _ in range(4):
        o = px
        c = o - 50 * point
        candles.append(Candle(t, o, o + 5 * point, c - 5 * point, c))
        px = c
        t += timedelta(minutes=5)
    o = px
    sweep_low = asia_low - 40 * point
    c = asia_low + 30 * point
    candles.append(Candle(t, o, max(o, c) + 10 * point, sweep_low, c))
    px = c
    t += timedelta(minutes=5)
    for delta in (40 * point, 30 * point, 20 * point):
        o = px
        c = o + delta
        candles.append(Candle(t, o, max(o, c) + 10 * point, min(o, c) - 10 * point, c))
        px = c
        t += timedelta(minutes=5)
    o = px
    c = asia_high - 40 * point
    candles.append(Candle(t, o, c + 15 * point, o - 5 * point, c))
    px = c
    t += timedelta(minutes=5)
    for _ in range(12):
        o = px
        c = o + 25 * point
        candles.append(Candle(t, o, c + 8 * point, o - 8 * point, c))
        px = c
        t += timedelta(minutes=5)
    return candles
