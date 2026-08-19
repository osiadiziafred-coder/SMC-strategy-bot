"""Reference implementation of the EA's core rules for offline verification."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence


def volume_digits(step: float) -> int:
    if step >= 1.0:
        return 0
    if step >= 0.1:
        return 1
    if step >= 0.01:
        return 2
    if step >= 0.001:
        return 3
    return 4


def normalize_volume(
    lots: float,
    minlot: float = 0.01,
    maxlot: float = 100.0,
    step: float = 0.01,
) -> float:
    if step <= 0:
        step = 0.01
    lots = math.floor(lots / step + 1.0e-8) * step
    lots = max(minlot, min(maxlot, lots))
    return round(lots, volume_digits(step))


def calculate_lot_size_from_balance(
    balance: float,
    starting_lot: float = 0.01,
    first_increase_balance: float = 150.0,
    balance_step: float = 100.0,
    lot_increase: float = 0.01,
    minlot: float = 0.01,
    maxlot: float = 100.0,
    step: float = 0.01,
) -> float:
    lots = starting_lot
    if balance + 1.0e-8 >= first_increase_balance:
        extra = math.floor((balance - first_increase_balance) / balance_step + 1.0e-10) + 1.0
        lots = starting_lot + extra * lot_increase
    if lots < 0.0:
        lots = 0.0
    return normalize_volume(lots, minlot, maxlot, step)


@dataclass
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float


def is_swing_high(rates: Sequence[Candle], i: int, strength: int) -> bool:
    n = len(rates)
    if strength < 1:
        return False
    if i - strength < 1:
        return False
    if i + strength >= n:
        return False
    h = rates[i].high
    for k in range(1, strength + 1):
        if rates[i - k].high >= h:
            return False
        if rates[i + k].high > h:
            return False
    return True


def is_swing_low(rates: Sequence[Candle], i: int, strength: int) -> bool:
    n = len(rates)
    if strength < 1:
        return False
    if i - strength < 1:
        return False
    if i + strength >= n:
        return False
    low = rates[i].low
    for k in range(1, strength + 1):
        if rates[i - k].low <= low:
            return False
        if rates[i + k].low < low:
            return False
    return True


def find_swing_highs(rates: Sequence[Candle], strength: int) -> List[int]:
    n = len(rates)
    out = []
    for i in range(strength + 1, n - strength):
        if is_swing_high(rates, i, strength):
            out.append(i)
    return out


def find_swing_lows(rates: Sequence[Candle], strength: int) -> List[int]:
    n = len(rates)
    out = []
    for i in range(strength + 1, n - strength):
        if is_swing_low(rates, i, strength):
            out.append(i)
    return out


def classify_hhhl(highs: Sequence[float], lows: Sequence[float]) -> str:
    if len(highs) < 2 or len(lows) < 2:
        return "NONE"
    hh = highs[0] > highs[1]
    lh = highs[0] < highs[1]
    hl = lows[0] > lows[1]
    ll = lows[0] < lows[1]
    if hh and hl:
        return "BULLISH"
    if lh and ll:
        return "BEARISH"
    return "NONE"


def detect_liquidity_sweep(
    rates: Sequence[Candle],
    level: float,
    direction: int,
    min_pierce: float = 0.5,
) -> Optional[float]:
    """direction > 0 = bullish sweep of a low; < 0 = bearish sweep of a high."""
    for i in range(1, min(36, len(rates))):
        if direction > 0:
            if rates[i].low >= level - min_pierce * 0.25:
                continue
            if level - rates[i].low < min_pierce:
                continue
            for k in range(i, max(0, i - 3) - 1, -1):
                if k < 1:
                    break
                if rates[k].close > level:
                    return rates[i].low
        else:
            if rates[i].high <= level + min_pierce * 0.25:
                continue
            if rates[i].high - level < min_pierce:
                continue
            for k in range(i, max(0, i - 3) - 1, -1):
                if k < 1:
                    break
                if rates[k].close < level:
                    return rates[i].high
    return None


def calculate_risk_reward(entry: float, sl: float, tp: float) -> float:
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk <= 0:
        return 0.0
    return reward / risk


def stop_distance_ok(entry: float, sl: float, point: float, max_points: int) -> bool:
    dist = abs(entry - sl)
    if dist <= 0:
        return False
    points = round(dist / point)
    return points <= max_points


def is_chasing(direction: int, price: float, entry: float, tp: float) -> bool:
    if tp == entry:
        return True
    if direction > 0:
        if price >= tp:
            return True
        if price > entry and (price - entry) > 0.35 * abs(tp - entry):
            return True
    else:
        if price <= tp:
            return True
        if price < entry and (entry - price) > 0.35 * abs(entry - tp):
            return True
    return False


def in_session(hour: int, start: int, end: int, use_session: bool) -> bool:
    if not use_session:
        return True
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def all_entry_checks(
    *,
    symbol_is_xauusdm: bool,
    trading_allowed: bool,
    market_open: bool,
    spread_ok: bool,
    open_positions: int,
    max_positions: int,
    h1_setup: bool,
    m5_confirm: bool,
    sl_valid: bool,
    tp_valid: bool,
    rr: float,
    min_rr: float,
    daily_loss_hit: bool,
    drawdown_hit: bool,
    lot_valid: bool,
) -> bool:
    return all(
        [
            symbol_is_xauusdm,
            trading_allowed,
            market_open,
            spread_ok,
            open_positions < max_positions,
            h1_setup,
            m5_confirm,
            sl_valid,
            tp_valid,
            rr + 1e-8 >= min_rr,
            not daily_loss_hit,
            not drawdown_hit,
            lot_valid,
        ]
    )
