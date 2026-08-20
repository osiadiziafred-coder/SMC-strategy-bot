from __future__ import annotations

from smc_robot.config import RobotConfig, Signal, Zone
from smc_robot.smc.candles import ensure_ohlc
from smc_robot.smc.fvg import detect_fvg, price_in_zone, unmitigated
from smc_robot.smc.order_blocks import detect_order_blocks
from smc_robot.smc.structure import detect_structure, infer_bias, recent_events


class SmcStrategy:
    """Multi-timeframe SMC entry model for XAUUSDM.

    H1 sets bias from the latest BOS / MSS / CHoCH.
    M15 must agree with a recent structure shift in the same direction.
    M5 times the entry on a tap of an unmitigated order block or FVG.
    """

    def __init__(self, config: RobotConfig | None = None) -> None:
        self.config = config or RobotConfig()

    def evaluate(self, h1, m15, m5) -> Signal | None:
        cfg = self.config
        h1 = ensure_ohlc(h1)
        m15 = ensure_ohlc(m15)
        m5 = ensure_ohlc(m5)
        if min(len(h1), len(m15), len(m5)) < 20:
            return None

        h1_events = detect_structure(h1, cfg.swing_left, cfg.swing_right)
        bias = infer_bias(h1, h1_events)
        if bias is None:
            return None

        m15_events = detect_structure(m15, cfg.swing_left, cfg.swing_right)
        m15_recent = recent_events(m15_events, len(m15) - 1, cfg.recent_event_bars)
        m15_aligned = any(e.direction == bias for e in m15_recent) or infer_bias(m15, m15_events) == bias
        if not m15_aligned:
            return None

        m5_events = detect_structure(m5, cfg.swing_left, cfg.swing_right)
        fvgs = detect_fvg(m5)
        obs = detect_order_blocks(m5, m5_events)
        zones = unmitigated(fvgs + obs, direction=bias)
        if not zones:
            return None

        last = m5.iloc[-1]
        tapped = [z for z in zones if price_in_zone(float(last["low"]), float(last["high"]), z)]
        if not tapped:
            return None
        zone = _nearest_zone(tapped, float(last["close"]))
        if len(m5) >= 2:
            prev_close = float(m5.iloc[-2]["close"])
            if zone.low <= prev_close <= zone.high:
                return None

        reasons = [f"H1 {bias} bias", "M15 structure aligned"]
        confluence = 2
        if any(e.kind in {"CHOCH", "MSS"} and e.direction == bias for e in m15_recent):
            reasons.append("M15 CHoCH/MSS")
            confluence += 1
        if any(e.kind == "BOS" and e.direction == bias for e in h1_events[-3:]):
            reasons.append("H1 BOS")
            confluence += 1
        else:
            reasons.append(f"H1 {bias} trend")
            confluence += 1
        if zone.kind == "FVG":
            reasons.append("M5 FVG tap")
            confluence += 1
        if zone.kind == "OB":
            reasons.append("M5 order block tap")
            confluence += 1
        m5_recent = recent_events(m5_events, len(m5) - 1, cfg.recent_event_bars)
        if any(e.kind in {"CHOCH", "MSS", "BOS"} and e.direction == bias for e in m5_recent):
            reasons.append("M5 structure")
            confluence += 1

        if confluence < cfg.min_confluence:
            return None

        entry = float(last["close"])
        sl, tp = _levels(bias, entry, zone, cfg.sl_buffer, cfg.risk_reward)
        if sl is None or tp is None:
            return None
        if abs(entry - sl) <= 0:
            return None

        side = "buy" if bias == "bullish" else "sell"
        return Signal(
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            confluence=confluence,
            reasons=tuple(reasons),
            zone_kind=zone.kind,
            time=last["time"],
        )


def _nearest_zone(zones: list[Zone], price: float) -> Zone:
    return min(zones, key=lambda z: min(abs(price - z.low), abs(price - z.high), abs(price - z.midpoint)))


def _levels(
    bias: str,
    entry: float,
    zone: Zone,
    buffer: float,
    rr: float,
) -> tuple[float | None, float | None]:
    # Invalidation is the tapped SMC zone (order block or FVG), not an old swing.
    if bias == "bullish":
        sl = zone.low - buffer
        if sl >= entry:
            return None, None
        return sl, entry + (entry - sl) * rr

    sl = zone.high + buffer
    if sl <= entry:
        return None, None
    return sl, entry - (sl - entry) * rr
