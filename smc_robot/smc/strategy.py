from __future__ import annotations

from smc_robot.config import Evaluation, LiquiditySweep, RobotConfig, Signal, Zone
from smc_robot.smc.candles import ensure_ohlc
from smc_robot.smc.fvg import detect_fvg, price_in_zone, unmitigated
from smc_robot.smc.liquidity import detect_liquidity_sweeps, detect_liquidity_zones, recent_sweeps, recent_zones
from smc_robot.smc.order_blocks import detect_order_blocks
from smc_robot.smc.structure import detect_structure, events_after, infer_bias, recent_events
from smc_robot.smc.swings import detect_swings


class SmcStrategy:
    """FredFx v1 SMC sequential entry model for XAUUSDm.

    Isolated signals are not trades. Every gate below must pass, in order:

    1. H1  — latest BOS / MSS / CHoCH sets bullish or bearish bias.
    2. M15 — structure agrees, a liquidity zone exists, and an unmitigated
             order block or FVG sits in the bias direction.
    3. M5  — liquidity sweep, then MSS / CHoCH / BOS in the bias direction,
             then a fresh tap of an unmitigated OB or FVG.
    4. Risk — SL sits behind the sweep / zone; TP is 2× that distance.
    """

    def __init__(self, config: RobotConfig | None = None) -> None:
        self.config = config or RobotConfig()

    def evaluate(self, h1, m15, m5) -> Signal | None:
        return self.diagnose(h1, m15, m5).signal

    def diagnose(self, h1, m15, m5) -> Evaluation:
        cfg = self.config
        h1 = ensure_ohlc(h1)
        m15 = ensure_ohlc(m15)
        m5 = ensure_ohlc(m5)
        if min(len(h1), len(m15), len(m5)) < 20:
            return Evaluation(None, "not enough bars", ("need at least 20 bars on H1, M15 and M5",))

        stages: list[str] = []

        h1_events = detect_structure(h1, cfg.swing_left, cfg.swing_right)
        bias = infer_bias(h1, h1_events)
        if bias is None:
            return Evaluation(None, "H1 has no market structure", tuple(stages))
        h1_kind = h1_events[-1].kind if h1_events else "trend"
        stages.append(f"H1 {bias} structure ({h1_kind})")

        m15_swings = detect_swings(m15, cfg.swing_left, cfg.swing_right)
        m15_events = detect_structure(m15, cfg.swing_left, cfg.swing_right, m15_swings)
        m15_recent = recent_events(m15_events, len(m15) - 1, cfg.recent_event_bars)
        m15_aligned = any(e.direction == bias for e in m15_recent) or infer_bias(m15, m15_events) == bias
        if not m15_aligned:
            return Evaluation(None, "M15 structure does not confirm H1", tuple(stages))
        stages.append("M15 structure confirms H1")

        m15_sweeps = detect_liquidity_sweeps(m15, cfg.swing_left, cfg.swing_right, m15_swings)
        m15_liq = detect_liquidity_zones(
            m15,
            cfg.swing_left,
            cfg.swing_right,
            cfg.equal_tolerance,
            m15_swings,
            m15_sweeps,
        )
        m15_liq_recent = [z for z in recent_zones(m15_liq, len(m15) - 1, cfg.recent_event_bars) if z.direction == bias]
        if not m15_liq_recent:
            m15_liq_recent = [z for z in m15_liq if z.direction == bias]
        if cfg.require_m15_liquidity and not m15_liq_recent:
            return Evaluation(None, "M15 has no liquidity zone in the H1 direction", tuple(stages))
        if m15_liq_recent:
            zone = m15_liq_recent[-1]
            stages.append(f"M15 {zone.side} {zone.kind} liquidity")

        m15_fvgs = detect_fvg(m15)
        m15_obs = detect_order_blocks(m15, m15_events)
        m15_pd = unmitigated(m15_fvgs + m15_obs, direction=bias)
        if cfg.require_m15_pd_array and not m15_pd:
            return Evaluation(None, "M15 has no unmitigated OB/FVG in the H1 direction", tuple(stages))
        if m15_pd:
            kinds = sorted({z.kind for z in m15_pd})
            stages.append(f"M15 premium/discount array ({'/'.join(kinds)})")

        m5_swings = detect_swings(m5, cfg.swing_left, cfg.swing_right)
        m5_events = detect_structure(m5, cfg.swing_left, cfg.swing_right, m5_swings)
        sweeps = detect_liquidity_sweeps(m5, cfg.swing_left, cfg.swing_right, m5_swings)
        m5_sweeps = [s for s in recent_sweeps(sweeps, len(m5) - 1, cfg.recent_event_bars) if s.direction == bias]
        if cfg.require_liquidity_sweep and not m5_sweeps:
            return Evaluation(None, "M5 has no liquidity sweep in the H1 direction", tuple(stages))
        sweep = m5_sweeps[-1] if m5_sweeps else None
        if sweep is not None:
            stages.append(f"M5 {sweep.kind} liquidity sweep")

        if sweep is not None:
            m5_after = events_after(m5_events, sweep.index, bias)
        else:
            m5_after = [e for e in recent_events(m5_events, len(m5) - 1, cfg.recent_event_bars) if e.direction == bias]
        if cfg.require_m5_structure_after_sweep and not m5_after:
            return Evaluation(None, "M5 has no MSS/CHoCH/BOS after the liquidity sweep", tuple(stages))
        if m5_after:
            confirm = m5_after[-1]
            stages.append(f"M5 {confirm.kind} {confirm.direction} after sweep")

        fvgs = detect_fvg(m5)
        obs = detect_order_blocks(m5, m5_events)
        zones = unmitigated(fvgs + obs, direction=bias)
        if not zones:
            return Evaluation(None, "M5 has no unmitigated OB/FVG to enter from", tuple(stages))

        last = m5.iloc[-1]
        tapped = [z for z in zones if price_in_zone(float(last["low"]), float(last["high"]), z)]
        if not tapped:
            return Evaluation(None, "M5 is not tapping an unmitigated OB/FVG", tuple(stages))
        zone = _nearest_zone(tapped, float(last["close"]))
        if len(m5) >= 2:
            prev_close = float(m5.iloc[-2]["close"])
            if zone.low <= prev_close <= zone.high:
                return Evaluation(None, "M5 zone tap is not fresh", tuple(stages))
        stages.append(f"M5 {zone.kind} tap")

        reasons = list(stages)
        confluence = len(reasons)
        entry = float(last["close"])
        sl, tp = _levels(bias, entry, zone, sweep, cfg.sl_buffer, cfg.risk_reward)
        if sl is None or tp is None or abs(entry - sl) <= 0:
            return Evaluation(None, "structure stop is invalid versus entry", tuple(stages))

        side = "buy" if bias == "bullish" else "sell"
        signal = Signal(
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            confluence=confluence,
            reasons=tuple(reasons),
            zone_kind=zone.kind,
            time=last["time"],
        )
        return Evaluation(signal, None, tuple(stages))


def _nearest_zone(zones: list[Zone], price: float) -> Zone:
    return min(zones, key=lambda z: min(abs(price - z.low), abs(price - z.high), abs(price - z.midpoint)))


def _levels(
    bias: str,
    entry: float,
    zone: Zone,
    sweep: LiquiditySweep | None,
    buffer: float,
    rr: float,
) -> tuple[float | None, float | None]:
    if bias == "bullish":
        sl = zone.low - buffer
        if sweep is not None:
            sl = min(sl, sweep.wick - buffer)
        if sl >= entry:
            return None, None
        return sl, entry + (entry - sl) * rr

    sl = zone.high + buffer
    if sweep is not None:
        sl = max(sl, sweep.wick + buffer)
    if sl <= entry:
        return None, None
    return sl, entry - (sl - entry) * rr
