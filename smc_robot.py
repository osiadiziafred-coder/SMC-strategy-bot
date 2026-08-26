#!/usr/bin/env python3
"""Single-file Python AI SMC robot for XAUUSDm on MetaTrader 5.

THIS IS PYTHON. Do not paste this file into MetaEditor / a .mq5 Expert Advisor.
MetaEditor only compiles MQL5. Use pyhonAI_SMC.mq5 for MetaEditor.

Save as smc_robot.py then:

    pip install numpy
    python smc_robot.py --self-test
    python smc_robot.py --mode paper

Live MT5 (Windows, MT5 terminal running):

    pip install numpy MetaTrader5
    set MT5_LOGIN / MT5_PASSWORD / MT5_SERVER
    python smc_robot.py --mode live
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import numpy as np

LOG = logging.getLogger("smc")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    symbol: str = "XAUUSDm"
    swing_n_internal: int = 2
    swing_n_external: int = 5
    equal_level_atr_mult: float = 0.15
    fvg_min_atr_mult: float = 0.10
    ob_lookback_bars: int = 12
    ob_impulse_atr_mult: float = 1.20
    ob_max_age_bars: int = 24
    structure_event_max_age_m30: int = 8
    structure_event_max_age_m15: int = 10
    sweep_lookback_bars: int = 6
    atr_period: int = 14
    min_score: float = 70.0
    reward_ratio: float = 2.0
    balance_per_lot_step: float = 100.0
    lot_step_per_balance: float = 0.01
    sl_buffer_atr_mult: float = 0.10
    breakeven_r: float = 1.0
    breakeven_buffer_points: float = 0.0
    max_positions: int = 1
    magic: int = 20250824
    comment: str = "SMC-AI"
    max_spread_points: float = 80.0
    max_slippage_points: float = 40.0
    max_quote_age_ms: int = 3000
    spread_spike_mult: float = 2.5
    spread_window: int = 20
    min_stop_points: float = 50.0
    atr_slow_period: int = 50
    low_atr_ratio: float = 0.60
    high_atr_ratio: float = 2.20
    choppy_efficiency: float = 0.18
    poll_seconds: int = 5
    analyze_on_closed_bar_only: bool = True
    bars_h1: int = 300
    bars_m30: int = 400
    bars_m15: int = 500
    w_h1_aligned: float = 20.0
    w_m30_confirmation: float = 15.0
    w_liquidity_sweep: float = 15.0
    w_order_block: float = 15.0
    w_fvg: float = 10.0
    w_bos: float = 5.0
    w_choch: float = 5.0
    w_mss: float = 10.0
    w_good_conditions: float = 10.0
    w_poor_conditions: float = -20.0
    w_h1_conflict: float = -25.0


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

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


@dataclass
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

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


@dataclass
class Swing:
    kind: SwingKind
    index: int
    time: datetime
    price: float


@dataclass
class StructureEvent:
    event_type: EventType
    direction: Direction
    index: int
    time: datetime
    level: float
    close: float


@dataclass
class Zone:
    kind: str
    direction: Direction
    index: int
    time: datetime
    low: float
    high: float
    extra: dict = field(default_factory=dict)

    def overlaps(self, low: float, high: float) -> bool:
        return low <= self.high and high >= self.low

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass
class LiquiditySweep:
    direction: Direction
    index: int
    time: datetime
    swept_price: float
    wick: float
    close: float
    equal_liquidity: bool = False


@dataclass
class LiquidityPool:
    kind: SwingKind
    price: float
    index: int
    equal: bool
    members: int


@dataclass
class MarketConditions:
    atr: float
    atr_ratio: float
    efficiency: float
    spread: float
    spread_ratio: float
    choppy: bool
    poor: bool
    reasons: list[str]


@dataclass
class TradePlan:
    direction: Direction
    entry: float
    sl: float
    tp: float
    risk: float
    lots: float
    sl_source: str


@dataclass
class ScoreBreakdown:
    total: float
    components: dict
    features: dict


@dataclass
class Signal:
    direction: Direction
    plan: TradePlan
    score: ScoreBreakdown
    sweep: Optional[LiquiditySweep]
    order_block: Optional[Zone]
    fvg: Optional[Zone]
    reason: str


@dataclass
class Decision:
    action: str
    reason: str
    score: Optional[ScoreBreakdown] = None
    signal: Optional[Signal] = None


@dataclass
class Position:
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


@dataclass
class Quote:
    bid: float
    ask: float
    time: datetime
    spread_points: float


@dataclass
class SymbolSpec:
    name: str
    point: float = 0.01
    digits: int = 2
    volume_min: float = 0.01
    volume_max: float = 50.0
    volume_step: float = 0.01
    trade_stops_level: int = 0
    filling_mode: int = 1


@dataclass
class TFAnalysis:
    candles: list[Candle]
    trend: Trend
    internal_swings: list[Swing]
    external_swings: list[Swing]
    events: list[StructureEvent]
    order_blocks: list[Zone]
    fvgs: list[Zone]
    pools: list[LiquidityPool]
    sweeps: list[LiquiditySweep]


# ---------------------------------------------------------------------------
# Indicators + SMC
# ---------------------------------------------------------------------------

def atr(candles: list[Candle], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    highs = np.array([c.high for c in candles])
    lows = np.array([c.low for c in candles])
    closes = np.array([c.close for c in candles])
    prev = np.roll(closes, 1)
    prev[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev), np.abs(lows - prev)))
    window = tr[-period:] if len(tr) >= period else tr
    return float(np.mean(window))


def efficiency_ratio(candles: list[Candle], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    window = candles[-period:]
    net = abs(window[-1].close - window[0].open)
    path = sum(c.range for c in window)
    return float(net / path) if path > 0 else 0.0


def detect_swings(candles: list[Candle], n: int) -> list[Swing]:
    if n < 1 or len(candles) < 2 * n + 1:
        return []
    swings: list[Swing] = []
    for i in range(n, len(candles) - n):
        c = candles[i]
        left, right = candles[i - n : i], candles[i + 1 : i + n + 1]
        if all(c.high > o.high for o in left) and all(c.high > o.high for o in right):
            swings.append(Swing(SwingKind.HIGH, i, c.time, c.high))
        if all(c.low < o.low for o in left) and all(c.low < o.low for o in right):
            swings.append(Swing(SwingKind.LOW, i, c.time, c.low))
    return swings


def last_swings(swings: list[Swing], kind: SwingKind, before: int, count: int = 2) -> list[Swing]:
    selected = [s for s in swings if s.kind == kind and s.index < before]
    return selected[-count:]


def classify_trend(swings: list[Swing], before: int) -> Trend:
    highs, lows = last_swings(swings, SwingKind.HIGH, before, 2), last_swings(swings, SwingKind.LOW, before, 2)
    if len(highs) < 2 or len(lows) < 2:
        return Trend.RANGING
    hh, hl = highs[-1].price > highs[-2].price, lows[-1].price > lows[-2].price
    lh, ll = highs[-1].price < highs[-2].price, lows[-1].price < lows[-2].price
    if hh and hl:
        return Trend.BULLISH
    if lh and ll:
        return Trend.BEARISH
    return Trend.RANGING


def _confirmed(swings, n, before, kind):
    return [s for s in swings if s.kind == kind and s.index < before and s.index + n < before]


def _event(etype, direction, i, candle, level):
    return StructureEvent(etype, direction, i, candle.time, level, candle.close)


def detect_structure_events(candles, n_int, n_ext):
    internal, external = detect_swings(candles, n_int), detect_swings(candles, n_ext)
    events = []
    start = max(2 * n_ext + 1, 2 * n_int + 1)
    for i in range(start, len(candles)):
        trend = classify_trend(external, i)
        c = candles[i]
        ih, il = _confirmed(internal, n_int, i, SwingKind.HIGH), _confirmed(internal, n_int, i, SwingKind.LOW)
        eh, el = _confirmed(external, n_ext, i, SwingKind.HIGH), _confirmed(external, n_ext, i, SwingKind.LOW)
        last_ih, last_il = (ih[-1] if ih else None), (il[-1] if il else None)
        last_eh, last_el = (eh[-1] if eh else None), (el[-1] if el else None)
        event = None
        if trend == Trend.BEARISH and last_eh and c.close > last_eh.price:
            event = _event(EventType.MSS, Direction.BUY, i, c, last_eh.price)
        elif trend == Trend.BULLISH and last_el and c.close < last_el.price:
            event = _event(EventType.MSS, Direction.SELL, i, c, last_el.price)
        elif trend == Trend.BEARISH and last_ih and c.close > last_ih.price:
            event = _event(EventType.CHOCH, Direction.BUY, i, c, last_ih.price)
        elif trend == Trend.BULLISH and last_il and c.close < last_il.price:
            event = _event(EventType.CHOCH, Direction.SELL, i, c, last_il.price)
        elif trend == Trend.BULLISH and last_ih and c.close > last_ih.price:
            event = _event(EventType.BOS, Direction.BUY, i, c, last_ih.price)
        elif trend == Trend.BEARISH and last_il and c.close < last_il.price:
            event = _event(EventType.BOS, Direction.SELL, i, c, last_il.price)
        elif trend == Trend.RANGING:
            if last_eh and c.close > last_eh.price:
                event = _event(EventType.MSS, Direction.BUY, i, c, last_eh.price)
            elif last_el and c.close < last_el.price:
                event = _event(EventType.MSS, Direction.SELL, i, c, last_el.price)
        if event:
            events.append(event)
    return events, classify_trend(external, len(candles)), internal, external


def recent_events(events, last_index, max_age, direction=None):
    out = [e for e in events if 0 <= last_index - e.index <= max_age]
    if direction is not None:
        out = [e for e in out if e.direction == direction]
    return out


def detect_order_blocks(candles, events, lookback, impulse_atr_mult, atr_period):
    if len(candles) < 5:
        return []
    min_impulse = impulse_atr_mult * atr(candles, atr_period)
    blocks, seen = [], set()
    for event in events:
        if event.event_type not in (EventType.BOS, EventType.MSS):
            continue
        start = max(0, event.index - lookback)
        ob_index = None
        for j in range(event.index - 1, start - 1, -1):
            if event.direction == Direction.BUY and candles[j].bearish:
                ob_index = j
                break
            if event.direction == Direction.SELL and candles[j].bullish:
                ob_index = j
                break
        if ob_index is None or ob_index in seen:
            continue
        obc = candles[ob_index]
        impulse = abs(candles[event.index].close - obc.close)
        if impulse < min_impulse:
            continue
        seen.add(ob_index)
        blocks.append(Zone("OB", event.direction, ob_index, obc.time, obc.low, obc.high, {"created_by": event.event_type.value}))
    return blocks


def unmitigated_obs(candles, blocks):
    live = []
    for b in blocks:
        mitigated = False
        for c in candles[b.index + 1 :]:
            if b.direction == Direction.BUY and c.close < b.low:
                mitigated = True
                break
            if b.direction == Direction.SELL and c.close > b.high:
                mitigated = True
                break
        if not mitigated:
            live.append(b)
    return live


def interacting_blocks(candles, blocks, direction, max_age):
    if not candles:
        return []
    last, idx, out = candles[-1], len(candles) - 1, []
    for b in blocks:
        if b.direction != direction or idx - b.index > max_age:
            continue
        if not b.overlaps(last.low, last.high) and not b.contains(last.close):
            continue
        if b.direction == Direction.BUY and last.close < b.low:
            continue
        if b.direction == Direction.SELL and last.close > b.high:
            continue
        out.append(b)
    return out


def detect_fvgs(candles, min_atr_mult, atr_period):
    if len(candles) < 3:
        return []
    min_size = min_atr_mult * atr(candles, atr_period)
    gaps = []
    for i in range(2, len(candles)):
        left, right = candles[i - 2], candles[i]
        if right.low > left.high and right.low - left.high >= min_size:
            gaps.append(Zone("FVG", Direction.BUY, i, right.time, left.high, right.low, {}))
        elif right.high < left.low and left.low - right.high >= min_size:
            gaps.append(Zone("FVG", Direction.SELL, i, right.time, right.high, left.low, {}))
    return gaps


def unfilled_fvgs(candles, gaps):
    live = []
    for g in gaps:
        filled = False
        for c in candles[g.index + 1 :]:
            if g.direction == Direction.BUY and c.low <= g.low:
                filled = True
                break
            if g.direction == Direction.SELL and c.high >= g.high:
                filled = True
                break
        if not filled:
            live.append(g)
    return live


def interacting_fvgs(candles, gaps, direction):
    if not candles:
        return []
    last, out = candles[-1], []
    for g in gaps:
        if g.direction != direction:
            continue
        if not g.overlaps(last.low, last.high) and not g.contains(last.close):
            continue
        if g.direction == Direction.BUY and last.close < g.low:
            continue
        if g.direction == Direction.SELL and last.close > g.high:
            continue
        out.append(g)
    return out


def build_pools(swings, candles, equal_atr_mult, atr_period):
    tol = equal_atr_mult * atr(candles, atr_period)
    pools = []
    for kind in (SwingKind.HIGH, SwingKind.LOW):
        selected = [s for s in swings if s.kind == kind]
        used = set()
        for i, swing in enumerate(selected):
            if i in used:
                continue
            cluster = [swing]
            used.add(i)
            for j in range(i + 1, len(selected)):
                if j not in used and abs(selected[j].price - swing.price) <= tol:
                    cluster.append(selected[j])
                    used.add(j)
            last = max(cluster, key=lambda s: s.index)
            pools.append(LiquidityPool(kind, sum(s.price for s in cluster) / len(cluster), last.index, len(cluster) >= 2, len(cluster)))
    return pools


def detect_sweeps(candles, pools):
    sweeps = []
    for i, c in enumerate(candles):
        for pool in pools:
            if pool.index >= i:
                continue
            if pool.kind == SwingKind.LOW and c.low < pool.price and c.close > pool.price:
                sweeps.append(LiquiditySweep(Direction.BUY, i, c.time, pool.price, c.low, c.close, pool.equal))
            elif pool.kind == SwingKind.HIGH and c.high > pool.price and c.close < pool.price:
                sweeps.append(LiquiditySweep(Direction.SELL, i, c.time, pool.price, c.high, c.close, pool.equal))
    best = {}
    for s in sweeps:
        key = (s.index, s.direction.value)
        prev = best.get(key)
        if prev is None or (s.equal_liquidity and not prev.equal_liquidity) or abs(s.wick - s.swept_price) > abs(prev.wick - prev.swept_price):
            best[key] = s
    return sorted(best.values(), key=lambda x: x.index)


def recent_sweeps(sweeps, last_index, lookback, direction):
    return [s for s in sweeps if s.direction == direction and 0 <= last_index - s.index <= lookback]


def analyze_conditions(candles, settings: Settings, spread, recent_spreads=None):
    a = atr(candles, settings.atr_period)
    slow = atr(candles, settings.atr_slow_period)
    ratio = (a / slow) if slow > 0 else 1.0
    eff = efficiency_ratio(candles, settings.atr_period)
    med = float(np.median(recent_spreads)) if recent_spreads else spread
    spr = (spread / med) if med > 0 else 1.0
    reasons = []
    choppy = eff < settings.choppy_efficiency and ratio <= 1.05
    if choppy:
        reasons.append("choppy")
    if ratio < settings.low_atr_ratio:
        reasons.append("low_vol")
    if ratio > settings.high_atr_ratio:
        reasons.append("extreme_vol")
    if spr >= settings.spread_spike_mult:
        reasons.append("spread_spike")
    return MarketConditions(a, ratio, eff, spread, spr, choppy, bool(reasons), reasons)


def analyze_tf(candles: list[Candle], s: Settings) -> TFAnalysis:
    events, trend, internal, external = detect_structure_events(candles, s.swing_n_internal, s.swing_n_external)
    obs = unmitigated_obs(candles, detect_order_blocks(candles, events, s.ob_lookback_bars, s.ob_impulse_atr_mult, s.atr_period))
    fvgs = unfilled_fvgs(candles, detect_fvgs(candles, s.fvg_min_atr_mult, s.atr_period))
    pools = build_pools(internal, candles, s.equal_level_atr_mult, s.atr_period)
    return TFAnalysis(candles, trend, internal, external, events, obs, fvgs, pools, detect_sweeps(candles, pools))


# ---------------------------------------------------------------------------
# Scoring, risk, engine
# ---------------------------------------------------------------------------

def extract_features(direction, h1, m30, m15, cond, s: Settings, sweep, ob, fvg):
    last, m30_last = len(m15.candles) - 1, len(m30.candles) - 1
    m30_ev = recent_events(m30.events, m30_last, s.structure_event_max_age_m30, direction)
    m15_ev = recent_events(m15.events, last, s.structure_event_max_age_m15, direction)

    def tv(trend):
        if trend == Trend.RANGING:
            return 0.0
        want = Trend.BULLISH if direction == Direction.BUY else Trend.BEARISH
        return 1.0 if trend == want else -1.0

    def has(evs, et):
        return 1.0 if any(e.event_type == et for e in evs) else 0.0

    h1v = tv(h1.trend)
    return {
        "h1_aligned": 1.0 if h1v > 0 else 0.0,
        "h1_conflict": 1.0 if h1v < 0 else 0.0,
        "m30_trend": tv(m30.trend),
        "m30_bos": has(m30_ev, EventType.BOS),
        "m30_choch": has(m30_ev, EventType.CHOCH),
        "m30_mss": has(m30_ev, EventType.MSS),
        "m15_bos": has(m15_ev, EventType.BOS),
        "m15_choch": has(m15_ev, EventType.CHOCH),
        "m15_mss": has(m15_ev, EventType.MSS),
        "sweep": 1.0 if sweep else 0.0,
        "sweep_equal": 1.0 if sweep and sweep.equal_liquidity else 0.0,
        "ob_interact": 1.0 if ob else 0.0,
        "fvg_interact": 1.0 if fvg else 0.0,
        "atr_ratio": cond.atr_ratio,
        "efficiency": cond.efficiency,
        "poor_conditions": 1.0 if cond.poor else 0.0,
    }


def rule_score(feat, s: Settings):
    parts = {}
    if feat["h1_aligned"] > 0:
        parts["h1_aligned"] = s.w_h1_aligned
    if feat["h1_conflict"] > 0:
        parts["h1_conflict"] = s.w_h1_conflict
    if feat["m30_bos"] or feat["m30_mss"] or feat["m30_choch"] or feat["m30_trend"] > 0:
        parts["m30_confirmation"] = s.w_m30_confirmation
    if feat["sweep"] > 0:
        parts["liquidity_sweep"] = s.w_liquidity_sweep + (3.0 if feat["sweep_equal"] else 0)
    if feat["ob_interact"] > 0:
        parts["order_block"] = s.w_order_block
    if feat["fvg_interact"] > 0:
        parts["fvg"] = s.w_fvg
    if feat["m15_bos"] > 0:
        parts["bos"] = s.w_bos
    if feat["m15_choch"] > 0:
        parts["choch"] = s.w_choch
    if feat["m15_mss"] > 0:
        parts["mss"] = s.w_mss
    if feat["poor_conditions"] > 0:
        parts["poor_conditions"] = s.w_poor_conditions
    elif feat["efficiency"] >= 0.30 and 0.8 <= feat["atr_ratio"] <= 1.8:
        parts["good_conditions"] = s.w_good_conditions
    return float(sum(parts.values())), parts


def find_setup_parts(direction, m30, m15, s: Settings):
    last, m30_last = len(m15.candles) - 1, len(m30.candles) - 1
    sweeps = recent_sweeps(m15.sweeps, last, s.sweep_lookback_bars, direction)
    if not sweeps:
        sweeps = recent_sweeps(m30.sweeps, m30_last, max(3, s.sweep_lookback_bars // 2), direction)
    obs = interacting_blocks(m15.candles, m15.order_blocks, direction, s.ob_max_age_bars) or interacting_blocks(
        m30.candles, m30.order_blocks, direction, s.ob_max_age_bars
    )
    fvgs = interacting_fvgs(m15.candles, m15.fvgs, direction) or interacting_fvgs(m30.candles, m30.fvgs, direction)
    m30_ev = recent_events(m30.events, m30_last, s.structure_event_max_age_m30, direction)
    return (sweeps[-1] if sweeps else None), (obs[-1] if obs else None), (fvgs[-1] if fvgs else None), m30_ev


def lots_from_balance(balance: float, spec: SymbolSpec, s: Settings) -> float:
    if balance < s.balance_per_lot_step or spec.volume_step <= 0:
        return 0.0
    raw = int(balance // s.balance_per_lot_step) * s.lot_step_per_balance
    lots = round(raw / spec.volume_step) * spec.volume_step
    lots = max(spec.volume_min, min(spec.volume_max, lots))
    prec = max(0, len(str(spec.volume_step).split(".")[-1]) if "." in str(spec.volume_step) else 0)
    lots = round(lots, prec)
    return 0.0 if lots < spec.volume_min else lots


def build_plan(direction, entry, sweep, ob, fvg, atr_value, balance, spec, s: Settings):
    buffer = s.sl_buffer_atr_mult * atr_value
    min_d = max(s.min_stop_points * spec.point, spec.trade_stops_level * spec.point, spec.point)
    if direction == Direction.BUY:
        cand = []
        if sweep:
            cand.append(("sweep_low", sweep.wick))
        if ob:
            cand.append(("order_block", ob.low))
        if fvg:
            cand.append(("fvg", fvg.low))
        if not cand:
            return None
        src, structural = min(cand, key=lambda x: x[1])
        sl = structural - buffer
        if entry - sl < min_d:
            sl = entry - min_d
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + s.reward_ratio * risk
    else:
        cand = []
        if sweep:
            cand.append(("sweep_high", sweep.wick))
        if ob:
            cand.append(("order_block", ob.high))
        if fvg:
            cand.append(("fvg", fvg.high))
        if not cand:
            return None
        src, structural = max(cand, key=lambda x: x[1])
        sl = structural + buffer
        if sl - entry < min_d:
            sl = entry + min_d
        risk = sl - entry
        if risk <= 0:
            return None
        tp = entry - s.reward_ratio * risk
    lots = lots_from_balance(balance, spec, s)
    if lots <= 0:
        return None
    return TradePlan(direction, entry, sl, tp, risk, lots, src)


def evaluate(h1, m30, m15, quote, spec, balance, s: Settings, recent_spreads=None) -> Decision:
    if len(h1) < 30 or len(m30) < 40 or len(m15) < 40:
        return Decision("skip", "insufficient_bars")
    h1a, m30a, m15a = analyze_tf(h1, s), analyze_tf(m30, s), analyze_tf(m15, s)
    cond = analyze_conditions(m15, s, quote.spread_points, recent_spreads)
    if h1a.trend == Trend.RANGING:
        return Decision("skip", "h1_ranging")
    direction = Direction.BUY if h1a.trend == Trend.BULLISH else Direction.SELL
    sweep, ob, fvg, m30_ev = find_setup_parts(direction, m30a, m15a, s)
    if m30a.trend != h1a.trend and not m30_ev:
        return Decision("skip", "m30_no_confirmation")
    if sweep is None:
        return Decision("skip", "no_recent_liquidity_sweep")
    if ob is None and fvg is None:
        return Decision("skip", "no_ob_or_fvg_interaction")
    if not recent_events(m15a.events, len(m15a.candles) - 1, s.structure_event_max_age_m15, direction):
        return Decision("skip", "no_m15_structure_confirmation")
    feat = extract_features(direction, h1a, m30a, m15a, cond, s, sweep, ob, fvg)
    total, parts = rule_score(feat, s)
    score = ScoreBreakdown(total, parts, feat)
    if total < s.min_score:
        return Decision("skip", f"score_{total:.1f}_below_{s.min_score}", score)
    entry = quote.ask if direction == Direction.BUY else quote.bid
    plan = build_plan(direction, entry, sweep, ob, fvg, cond.atr, balance, spec, s)
    if plan is None:
        return Decision("skip", "invalid_trade_plan", score)
    sig = Signal(direction, plan, score, sweep, ob, fvg, "smc_confluence")
    return Decision(direction.value.lower(), "take_setup", score, sig)


# ---------------------------------------------------------------------------
# Brokers + robot
# ---------------------------------------------------------------------------

class ExecutionGuard:
    def __init__(self, s: Settings):
        self.s = s
        self._spreads: deque[float] = deque(maxlen=s.spread_window)

    def observe(self, pts):
        self._spreads.append(pts)

    def recent(self):
        return list(self._spreads)

    def check(self, quote: Quote, spec: SymbolSpec):
        now = datetime.now(timezone.utc)
        qt = quote.time if quote.time.tzinfo else quote.time.replace(tzinfo=timezone.utc)
        age = (now - qt).total_seconds() * 1000.0
        if age > self.s.max_quote_age_ms:
            return False, f"stale_quote_{age:.0f}ms"
        if quote.spread_points > self.s.max_spread_points:
            return False, f"spread_{quote.spread_points:.1f}"
        if self._spreads:
            med = sorted(self._spreads)[len(self._spreads) // 2]
            if med > 0 and quote.spread_points >= med * self.s.spread_spike_mult:
                return False, "spread_spike"
        if quote.ask <= 0 or quote.bid <= 0 or quote.ask < quote.bid:
            return False, "invalid_quote"
        return True, "ok"


class PaperBroker:
    def __init__(self, spec=None, balance=1000.0, candles_by_tf=None, bid=2000.0, ask=2000.25, quote_time=None):
        self.spec = spec or SymbolSpec("XAUUSDm")
        self.balance = balance
        self.candles_by_tf = candles_by_tf or {}
        self.bid, self.ask = bid, ask
        self.quote_time = quote_time or datetime.now(timezone.utc)
        self.positions: list[Position] = []
        self._ticket = 1

    def connect(self):
        pass

    def shutdown(self):
        pass

    def symbol_spec(self, symbol):
        return self.spec

    def account_balance(self):
        return self.balance

    def candles(self, symbol, tf, count):
        return self.candles_by_tf.get(tf, [])[-count:]

    def quote(self, symbol):
        spread = (self.ask - self.bid) / self.spec.point if self.spec.point else 0.0
        return Quote(self.bid, self.ask, self.quote_time, spread)

    def open_positions(self, symbol, magic):
        return [p for p in self.positions if p.symbol == symbol and p.magic == magic]

    def market_order(self, symbol, direction, lots, sl, tp, deviation_points, magic, comment):
        price = self.ask if direction == Direction.BUY else self.bid
        pos = Position(self._ticket, symbol, direction, lots, price, sl, tp, sl, abs(price - sl), False, magic, comment)
        self._ticket += 1
        self.positions.append(pos)
        return pos

    def modify_sl(self, position, sl):
        upd = replace(position, sl=sl)
        self.positions = [upd if p.ticket == position.ticket else p for p in self.positions]
        return upd


class MT5Broker:
    TF = {"M15": 15, "M30": 30, "H1": 16385}

    def __init__(self, login=None, password=None, server=None, path=None):
        self.login, self.password, self.server, self.path = login, password, server, path
        self._mt5 = None

    def connect(self):
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("Install MetaTrader5 on Windows: pip install MetaTrader5") from exc
        self._mt5 = mt5
        ok = mt5.initialize(self.path) if self.path else mt5.initialize()
        if not ok:
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        if self.login and not mt5.login(self.login, password=self.password or "", server=self.server or ""):
            raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")

    def shutdown(self):
        if self._mt5:
            self._mt5.shutdown()

    def _r(self):
        if self._mt5 is None:
            raise RuntimeError("MT5 not connected")
        return self._mt5

    def symbol_spec(self, symbol):
        mt5 = self._r()
        info = mt5.symbol_info(symbol)
        if info is None:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Unknown symbol {symbol}")
        return SymbolSpec(info.name, float(info.point), int(info.digits), float(info.volume_min),
                          float(info.volume_max), float(info.volume_step), int(info.trade_stops_level), int(info.filling_mode))

    def account_balance(self):
        info = self._r().account_info()
        if info is None:
            raise RuntimeError("account_info failed")
        return float(info.balance)

    def candles(self, symbol, tf, count):
        mt5 = self._r()
        rates = mt5.copy_rates_from_pos(symbol, self.TF[tf], 0, count)
        if rates is None:
            raise RuntimeError(f"copy_rates failed: {mt5.last_error()}")
        out = []
        for row in rates:
            out.append(Candle(datetime.fromtimestamp(int(row["time"]), tz=timezone.utc),
                              float(row["open"]), float(row["high"]), float(row["low"]),
                              float(row["close"]), float(row["tick_volume"])))
        return out

    def quote(self, symbol):
        mt5 = self._r()
        tick, info = mt5.symbol_info_tick(symbol), mt5.symbol_info(symbol)
        if tick is None or info is None:
            raise RuntimeError("quote failed")
        point = float(info.point) or 0.01
        return Quote(float(tick.bid), float(tick.ask), datetime.fromtimestamp(int(tick.time), tz=timezone.utc),
                     (float(tick.ask) - float(tick.bid)) / point)

    def open_positions(self, symbol, magic):
        mt5 = self._r()
        positions = mt5.positions_get(symbol=symbol) or []
        out = []
        for pos in positions:
            if int(pos.magic) != magic:
                continue
            d = Direction.BUY if pos.type == 0 else Direction.SELL
            entry, sl = float(pos.price_open), float(pos.sl)
            out.append(Position(int(pos.ticket), pos.symbol, d, float(pos.volume), entry, sl, float(pos.tp),
                                sl, abs(entry - sl), False, int(pos.magic), str(pos.comment)))
        return out

    def market_order(self, symbol, direction, lots, sl, tp, deviation_points, magic, comment):
        mt5 = self._r()
        spec = self.symbol_spec(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError("No tick")
        otype = mt5.ORDER_TYPE_BUY if direction == Direction.BUY else mt5.ORDER_TYPE_SELL
        price = float(tick.ask) if direction == Direction.BUY else float(tick.bid)
        fill_mode = mt5.ORDER_FILLING_IOC
        if spec.filling_mode & getattr(mt5, "SYMBOL_FILLING_FOK", 2):
            fill_mode = mt5.ORDER_FILLING_FOK
        elif spec.filling_mode & getattr(mt5, "SYMBOL_FILLING_RETURN", 4):
            fill_mode = mt5.ORDER_FILLING_RETURN
        result = mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lots, "type": otype,
            "price": price, "sl": sl, "tp": tp, "deviation": deviation_points, "magic": magic,
            "comment": comment, "type_time": mt5.ORDER_TIME_GTC, "type_filling": fill_mode,
        })
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"order_send failed: {mt5.last_error()}")
        fill = float(result.price) if result.price else price
        return Position(int(result.order), symbol, direction, lots, fill, sl, tp, sl, abs(fill - sl), False, magic, comment)

    def modify_sl(self, position, sl):
        mt5 = self._r()
        result = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": position.symbol,
                                 "position": position.ticket, "sl": sl, "tp": position.tp})
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"modify SL failed: {mt5.last_error()}")
        return replace(position, sl=sl, breakeven_applied=True)


class PositionManager:
    def __init__(self, broker, s: Settings):
        self.broker, self.s = broker, s

    def can_enter(self, symbol):
        return len(self.broker.open_positions(symbol, self.s.magic)) < self.s.max_positions

    def manage(self, symbol, quote: Quote):
        for p in self.broker.open_positions(symbol, self.s.magic):
            self._be(p, quote)

    def _be(self, p: Position, quote: Quote):
        if p.breakeven_applied or p.initial_risk <= 0:
            return
        if p.direction == Direction.BUY and p.sl >= p.entry > 0:
            return
        if p.direction == Direction.SELL and 0 < p.sl <= p.entry:
            return
        buf = self.s.breakeven_buffer_points * 0.01
        if p.direction == Direction.BUY and quote.bid - p.entry >= self.s.breakeven_r * p.initial_risk:
            new_sl = p.entry + buf
            if new_sl > p.sl:
                LOG.info("BE BUY ticket=%s sl=%.3f", p.ticket, new_sl)
                self.broker.modify_sl(p, new_sl)
        elif p.direction == Direction.SELL and p.entry - quote.ask >= self.s.breakeven_r * p.initial_risk:
            new_sl = p.entry - buf
            if new_sl < p.sl or p.sl == 0:
                LOG.info("BE SELL ticket=%s sl=%.3f", p.ticket, new_sl)
                self.broker.modify_sl(p, new_sl)


class SmcRobot:
    def __init__(self, broker, s: Settings, dry_run=False):
        self.broker, self.s, self.dry_run = broker, s, dry_run
        self.manager = PositionManager(broker, s)
        self.guard = ExecutionGuard(s)
        self._last_bar = None

    def run_forever(self):
        self.broker.connect()
        LOG.info("SMC robot started symbol=%s dry_run=%s", self.s.symbol, self.dry_run)
        try:
            while True:
                try:
                    LOG.info("step=%s", self.step())
                except Exception:
                    LOG.exception("step failed")
                time.sleep(self.s.poll_seconds)
        except KeyboardInterrupt:
            LOG.info("stopped")
        finally:
            self.broker.shutdown()

    def step(self) -> str:
        sym, spec = self.s.symbol, self.broker.symbol_spec(self.s.symbol)
        quote = self.broker.quote(sym)
        self.guard.observe(quote.spread_points)
        self.manager.manage(sym, quote)
        if not self.manager.can_enter(sym):
            return "manage_open_position"
        if self.s.analyze_on_closed_bar_only:
            probe = self.broker.candles(sym, "M15", 3)
            if not probe:
                return "no_data"
            if self._last_bar is not None and probe[-1].time <= self._last_bar:
                return "wait_new_bar"
            self._last_bar = probe[-1].time
        ok, reason = self.guard.check(quote, spec)
        if not ok:
            return f"blocked:{reason}"
        h1 = self.broker.candles(sym, "H1", self.s.bars_h1)
        m30 = self.broker.candles(sym, "M30", self.s.bars_m30)
        m15 = self.broker.candles(sym, "M15", self.s.bars_m15)
        if self.s.analyze_on_closed_bar_only:
            h1, m30, m15 = h1[:-1] or h1, m30[:-1] or m30, m15[:-1] or m15
        d = evaluate(h1, m30, m15, quote, spec, self.broker.account_balance(), self.s, self.guard.recent())
        if d.signal is None:
            return d.reason
        plan = d.signal.plan
        if self.dry_run:
            LOG.info("DRY %s lots=%.2f entry=%.3f sl=%.3f tp=%.3f score=%.1f",
                     plan.direction.value, plan.lots, plan.entry, plan.sl, plan.tp, d.signal.score.total)
            return "dry_run_signal"
        pos = self.broker.market_order(sym, plan.direction, plan.lots, plan.sl, plan.tp,
                                       int(self.s.max_slippage_points), self.s.magic, self.s.comment)
        LOG.info("filled ticket=%s entry=%.3f", pos.ticket, pos.entry)
        return "order_sent"


# ---------------------------------------------------------------------------
# Self-test helpers
# ---------------------------------------------------------------------------

def candles_from_ohlc(rows, minutes=15):
    t = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out = []
    for o, h, l, c in rows:
        out.append(Candle(t, o, h, l, c))
        t += timedelta(minutes=minutes)
    return out


def structure_from_swings(points, n_bars, minutes, wick=0.25, extra_n=5):
    xs = np.array([i for i, _, _ in points], dtype=float)
    ys = np.array([p for _, _, p in points], dtype=float)
    closes = [float(np.interp(i, xs, ys)) for i in range(n_bars)]
    rows = []
    kind_at = {i: (k, p) for i, k, p in points}
    for i, close in enumerate(closes):
        o = closes[i - 1] if i else close
        h, l = max(o, close) + wick, min(o, close) - wick
        if i in kind_at:
            k, price = kind_at[i]
            if k == "H":
                h, close, o = price, price - wick, price - 2 * wick
                l = min(o, close) - wick
            else:
                l, close, o = price, price + wick, price + 2 * wick
                h = max(o, close) + wick
        rows.append((o, h, l, close))
    for index, kind, price in points:
        for j in range(max(0, index - extra_n), min(n_bars, index + extra_n + 1)):
            if j == index:
                continue
            o, h, l, c = rows[j]
            if kind == "H" and h >= price:
                h = price - 0.15
                c, o = min(c, h - 0.05), min(o, h - 0.05)
                l = min(l, o, c) - wick
            if kind == "L" and l <= price:
                l = price + 0.15
                c, o = max(c, l + 0.05), max(o, l + 0.05)
                h = max(h, o, c) + wick
            rows[j] = (o, h, l, c)
    return candles_from_ohlc(rows, minutes)


def bullish_structure(n=96, minutes=60):
    return structure_from_swings(
        [(8, "L", 2000.0), (22, "H", 2024.0), (36, "L", 2008.0),
         (50, "H", 2036.0), (64, "L", 2016.0), (78, "H", 2048.0)],
        n, minutes,
    )


def _set(c, o, h, l, cl):
    return replace(c, open=o, high=h, low=l, close=cl)


def m15_buy_setup():
    candles = [replace(c) for c in bullish_structure(110, 15)]
    for j in range(79, 110):
        candles[j] = _set(candles[j], 2042.0, 2043.4, 2041.2, 2042.2)
    candles[93] = _set(candles[93], 2041.2, 2043.0, 2040.8, 2042.4)
    for j in (91, 92, 94, 95):
        candles[j] = _set(candles[j], 2041.0, 2042.4, 2040.2, 2041.4)
    candles[100] = _set(candles[100], 2037.6, 2038.4, 2036.2, 2036.9)
    for j in (98, 99, 101, 102):
        candles[j] = _set(candles[j], 2038.0, 2039.2, 2037.5, 2038.3)
    candles[103] = _set(candles[103], 2037.4, 2038.8, 2035.3, 2037.8)
    candles[104] = _set(candles[104], 2038.1, 2038.5, 2036.4, 2036.7)
    candles[105] = _set(candles[105], 2036.8, 2041.8, 2036.6, 2041.4)
    candles[106] = _set(candles[106], 2041.5, 2045.2, 2041.2, 2044.8)
    candles[107] = _set(candles[107], 2044.6, 2045.0, 2041.0, 2041.6)
    candles[108] = _set(candles[108], 2041.5, 2042.4, 2040.4, 2041.0)
    candles[109] = _set(candles[109], 2041.2, 2042.6, 2037.2, 2039.8)
    return candles


def self_test() -> int:
    s, spec = Settings(), SymbolSpec("XAUUSDm")
    assert lots_from_balance(100, spec, s) == 0.01
    assert lots_from_balance(500, spec, s) == 0.05
    assert lots_from_balance(1000, spec, s) == 0.10
    sweep = LiquiditySweep(Direction.BUY, 10, datetime.now(timezone.utc), 1990, 1988, 1992)
    plan = build_plan(Direction.BUY, 2000, sweep, None, None, 5, 1000, spec, replace(s, sl_buffer_atr_mult=0))
    assert plan and plan.sl == 1988 and abs(plan.tp - 2024) < 1e-9
    rows = [(100, 101, 99.5, 100.4), (100.5, 106, 100.4, 105.5), (105.6, 107, 103.5, 106.2)]
    gaps = detect_fvgs(candles_from_ohlc(rows), 0.0, 14)
    assert gaps and gaps[0].low == 101.0 and gaps[0].high == 103.5
    h1, m30, m15 = bullish_structure(96, 60), bullish_structure(96, 30), m15_buy_setup()
    assert analyze_tf(h1, s).trend == Trend.BULLISH
    last = m15[-1]
    d = evaluate(h1, m30, m15, Quote(last.close - 0.1, last.close, datetime.now(timezone.utc), 20), spec, 1000, s, [20, 20])
    assert d.signal is not None, d.reason
    broker = PaperBroker(balance=1000, candles_by_tf={"H1": h1, "M30": m30, "M15": m15},
                         bid=last.close - 0.1, ask=last.close, quote_time=datetime.now(timezone.utc))
    robot = SmcRobot(broker, replace(s, analyze_on_closed_bar_only=False), dry_run=False)
    assert robot.step() == "order_sent"
    assert robot.step() == "manage_open_position"
    print("SELF-TEST PASSED")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Python AI SMC robot for XAUUSDm")
    p.add_argument("--mode", choices=("live", "dry", "paper"), default="paper")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.self_test:
        return self_test()
    s = Settings()
    if args.mode == "paper":
        broker, dry = PaperBroker(), False
    else:
        login = os.getenv("MT5_LOGIN")
        broker = MT5Broker(int(login) if login else None, os.getenv("MT5_PASSWORD"),
                           os.getenv("MT5_SERVER"), os.getenv("MT5_PATH") or None)
        dry = args.mode == "dry"
    SmcRobot(broker, s, dry_run=dry).run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
