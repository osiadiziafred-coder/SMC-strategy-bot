from __future__ import annotations

import numpy as np
import pandas as pd

from smc_robot.config import StructureEvent, Swing
from smc_robot.smc.candles import ensure_ohlc
from smc_robot.smc.swings import detect_swings


def detect_structure(
    df: pd.DataFrame,
    left: int = 2,
    right: int = 2,
    swings: list[Swing] | None = None,
) -> list[StructureEvent]:
    """Detect BOS, CHoCH and MSS from swing breaks.

    Trend starts undefined. The first swing break is tagged BOS.
    A later break in the same direction is BOS (continuation).
    A break against the current trend is CHoCH. If that reversal candle
    also shows displacement, an MSS event is recorded on the same bar.
    """
    src = ensure_ohlc(df)
    opens = src["open"].to_numpy(dtype=float)
    closes = src["close"].to_numpy(dtype=float)
    times = src["time"].tolist()
    swings = list(swings) if swings is not None else detect_swings(src, left=left, right=right)
    bodies = np.abs(closes - opens)

    events: list[StructureEvent] = []
    last_high: Swing | None = None
    last_low: Swing | None = None
    trend: str | None = None
    used_highs: set[int] = set()
    used_lows: set[int] = set()

    swing_ready_at: dict[int, list[Swing]] = {}
    for swing in swings:
        swing_ready_at.setdefault(swing.index + right, []).append(swing)

    for i in range(len(src)):
        for swing in swing_ready_at.get(i, []):
            if swing.kind == "high":
                last_high = swing
            else:
                last_low = swing

        if last_high is not None and last_high.index not in used_highs and last_high.index < i:
            if closes[i] > last_high.price:
                if trend in (None, "bullish"):
                    events.append(_event(i, times, "BOS", "bullish", last_high.price, closes[i]))
                else:
                    events.append(_event(i, times, "CHOCH", "bullish", last_high.price, closes[i]))
                    if _is_displacement(bodies, i):
                        events.append(_event(i, times, "MSS", "bullish", last_high.price, closes[i]))
                trend = "bullish"
                used_highs.add(last_high.index)

        if last_low is not None and last_low.index not in used_lows and last_low.index < i:
            if closes[i] < last_low.price:
                if trend in (None, "bearish"):
                    events.append(_event(i, times, "BOS", "bearish", last_low.price, closes[i]))
                else:
                    events.append(_event(i, times, "CHOCH", "bearish", last_low.price, closes[i]))
                    if _is_displacement(bodies, i):
                        events.append(_event(i, times, "MSS", "bearish", last_low.price, closes[i]))
                trend = "bearish"
                used_lows.add(last_low.index)

    return events


def _event(index: int, times, kind: str, direction: str, broken: float, close: float) -> StructureEvent:
    return StructureEvent(
        index=index,
        time=times[index],
        kind=kind,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        broken_price=float(broken),
        close=float(close),
    )


def _is_displacement(bodies: np.ndarray, index: int, lookback: int = 10, multiple: float = 1.5) -> bool:
    start = max(0, index - lookback)
    window = bodies[start:index]
    if window.size == 0:
        return True
    avg = float(window.mean())
    return avg <= 0 or float(bodies[index]) >= avg * multiple


def last_bias(events: list[StructureEvent]) -> str | None:
    if not events:
        return None
    return events[-1].direction


def infer_bias(df: pd.DataFrame, events: list[StructureEvent] | None = None, lookback: int = 10) -> str | None:
    """Prefer the latest BOS/CHoCH/MSS; otherwise use higher-high / lower-low trend."""
    if events:
        bias = last_bias(events)
        if bias:
            return bias
    src = ensure_ohlc(df)
    if len(src) < lookback + 1:
        return None
    last = src.iloc[-1]
    prev = src.iloc[-lookback - 1]
    if float(last["high"]) > float(prev["high"]) and float(last["low"]) >= float(prev["low"]):
        return "bullish"
    if float(last["low"]) < float(prev["low"]) and float(last["high"]) <= float(prev["high"]):
        return "bearish"
    if float(last["close"]) > float(prev["close"]):
        return "bullish"
    if float(last["close"]) < float(prev["close"]):
        return "bearish"
    return None


def recent_events(events: list[StructureEvent], bar_index: int, lookback: int) -> list[StructureEvent]:
    return [e for e in events if 0 <= bar_index - e.index <= lookback]
