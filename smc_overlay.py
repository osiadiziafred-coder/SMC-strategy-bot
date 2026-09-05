"""SMC overlay rules used by PythonML_SMC_Bridge.mq5 (display only).

These detectors match the Expert Advisor. They never produce BUY/SELL.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DIR_NONE = 0
DIR_BULL = 1
DIR_BEAR = -1
KIND_BOS = 1
KIND_CHOCH = 2
KIND_MSS = 3
ZONE_FVG = 1
ZONE_OB = 2
SWING_HIGH = 1
SWING_LOW = -1


@dataclass
class Swing:
    index: int
    price: float
    kind: int


@dataclass
class Event:
    index: int
    kind: int
    direction: int
    broken: float


@dataclass
class Zone:
    start_index: int
    end_index: int
    low: float
    high: float
    direction: int
    kind: int
    mitigated: bool = False


@dataclass
class Sweep:
    index: int
    direction: int
    swept_price: float
    wick: float
    equal_extra: bool = False
    members: int = 1


@dataclass
class Pool:
    kind: int
    price: float
    index: int
    equal: bool
    members: int


@dataclass
class Snapshot:
    bias: int = DIR_NONE
    events: list[Event] = field(default_factory=list)
    sweeps: list[Sweep] = field(default_factory=list)
    fvgs: list[Zone] = field(default_factory=list)
    obs: list[Zone] = field(default_factory=list)
    equal_pools: list[Pool] = field(default_factory=list)

    def last_of(self, kind: int) -> Event | None:
        for event in reversed(self.events):
            if event.kind == kind:
                return event
        return None

    def last_sweep(self, equal_extra: bool | None = None) -> Sweep | None:
        for sweep in reversed(self.sweeps):
            if equal_extra is None or sweep.equal_extra is equal_extra:
                return sweep
        return None

    def last_zone(self, kind: int) -> Zone | None:
        zones = self.fvgs if kind == ZONE_FVG else self.obs
        for zone in reversed(zones):
            if not zone.mitigated:
                return zone
        return None


def _max_of(values: list[float], start: int, end_exclusive: int) -> float:
    return max(values[start:end_exclusive])


def _min_of(values: list[float], start: int, end_exclusive: int) -> float:
    return min(values[start:end_exclusive])


def detect_swings(
    high: list[float],
    low: list[float],
    left: int = 2,
    right: int = 2,
) -> list[Swing]:
    n = len(high)
    swings: list[Swing] = []
    if n < left + right + 1:
        return swings
    for i in range(left, n - right):
        if high[i] > _max_of(high, i - left, i) and high[i] >= _max_of(high, i + 1, i + right + 1):
            swings.append(Swing(i, high[i], SWING_HIGH))
        if low[i] < _min_of(low, i - left, i) and low[i] <= _min_of(low, i + 1, i + right + 1):
            swings.append(Swing(i, low[i], SWING_LOW))
    return swings


def atr(high: list[float], low: list[float], close: list[float], period: int = 14) -> float:
    n = len(close)
    if n < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, n):
        tr = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        trs.append(tr)
    if not trs:
        return 0.0
    use = trs[-period:] if period > 0 else trs
    return sum(use) / len(use)


def build_equal_pools(
    swings: list[Swing],
    high: list[float],
    low: list[float],
    close: list[float],
    equal_atr_mult: float = 0.15,
) -> list[Pool]:
    tolerance = equal_atr_mult * atr(high, low, close)
    pools: list[Pool] = []
    for kind in (SWING_HIGH, SWING_LOW):
        selected = [s for s in swings if s.kind == kind]
        used = [False] * len(selected)
        for i, swing in enumerate(selected):
            if used[i]:
                continue
            cluster = [swing]
            used[i] = True
            for j in range(i + 1, len(selected)):
                if used[j]:
                    continue
                if abs(selected[j].price - swing.price) <= tolerance:
                    cluster.append(selected[j])
                    used[j] = True
            price = sum(s.price for s in cluster) / len(cluster)
            last = max(cluster, key=lambda s: s.index)
            pools.append(
                Pool(
                    kind=kind,
                    price=price,
                    index=last.index,
                    equal=len(cluster) >= 2,
                    members=len(cluster),
                )
            )
    return pools


def _is_displacement(open_: list[float], close: list[float], index: int, lookback: int = 10) -> bool:
    bodies = [abs(close[i] - open_[i]) for i in range(max(0, index - lookback), index)]
    if not bodies:
        return True
    avg = sum(bodies) / len(bodies)
    return avg <= 0 or abs(close[index] - open_[index]) >= avg * 1.5


def detect_structure(
    open_: list[float],
    high: list[float],
    low: list[float],
    close: list[float],
    left: int = 2,
    right: int = 2,
) -> list[Event]:
    n = len(close)
    swings = detect_swings(high, low, left, right)
    events: list[Event] = []
    last_high_i = -1
    last_low_i = -1
    last_high_p = 0.0
    last_low_p = 0.0
    trend = DIR_NONE
    used_high = [False] * n
    used_low = [False] * n

    for i in range(n):
        for swing in swings:
            if swing.index + right != i:
                continue
            if swing.kind == SWING_HIGH:
                last_high_i = swing.index
                last_high_p = swing.price
            else:
                last_low_i = swing.index
                last_low_p = swing.price

        if last_high_i >= 0 and not used_high[last_high_i] and last_high_i < i:
            if close[i] > last_high_p:
                kind = KIND_BOS if trend in (DIR_NONE, DIR_BULL) else KIND_CHOCH
                events.append(Event(i, kind, DIR_BULL, last_high_p))
                if kind == KIND_CHOCH and _is_displacement(open_, close, i):
                    events.append(Event(i, KIND_MSS, DIR_BULL, last_high_p))
                trend = DIR_BULL
                used_high[last_high_i] = True

        if last_low_i >= 0 and not used_low[last_low_i] and last_low_i < i:
            if close[i] < last_low_p:
                kind = KIND_BOS if trend in (DIR_NONE, DIR_BEAR) else KIND_CHOCH
                events.append(Event(i, kind, DIR_BEAR, last_low_p))
                if kind == KIND_CHOCH and _is_displacement(open_, close, i):
                    events.append(Event(i, KIND_MSS, DIR_BEAR, last_low_p))
                trend = DIR_BEAR
                used_low[last_low_i] = True
    return events


def detect_sweeps(
    high: list[float],
    low: list[float],
    close: list[float],
    left: int = 2,
    right: int = 2,
    equal_atr_mult: float = 0.15,
) -> tuple[list[Sweep], list[Pool]]:
    n = len(close)
    swings = detect_swings(high, low, left, right)
    pools = build_equal_pools(swings, high, low, close, equal_atr_mult)
    sweeps: list[Sweep] = []
    used: set[tuple[int, int]] = set()

    for i in range(n):
        best: Sweep | None = None
        for pool in pools:
            if pool.index >= i:
                continue
            hit = False
            direction = DIR_NONE
            wick = 0.0
            if pool.kind == SWING_LOW and low[i] < pool.price and close[i] > pool.price:
                hit = True
                direction = DIR_BULL
                wick = low[i]
            elif pool.kind == SWING_HIGH and high[i] > pool.price and close[i] < pool.price:
                hit = True
                direction = DIR_BEAR
                wick = high[i]
            if not hit:
                continue
            candidate = Sweep(
                index=i,
                direction=direction,
                swept_price=pool.price,
                wick=wick,
                equal_extra=pool.equal and pool.members >= 2,
                members=pool.members,
            )
            if best is None:
                best = candidate
                continue
            if candidate.equal_extra and not best.equal_extra:
                best = candidate
                continue
            if abs(candidate.wick - candidate.swept_price) > abs(best.wick - best.swept_price):
                best = candidate
        if best is not None and (best.index, best.direction) not in used:
            sweeps.append(best)
            used.add((best.index, best.direction))
    return sweeps, [p for p in pools if p.equal]


def detect_fvg(high: list[float], low: list[float], close: list[float]) -> list[Zone]:
    n = len(close)
    zones: list[Zone] = []
    if n < 3:
        return zones
    for i in range(1, n - 1):
        if low[i + 1] > high[i - 1]:
            zones.append(
                Zone(
                    start_index=i - 1,
                    end_index=i + 1,
                    low=high[i - 1],
                    high=low[i + 1],
                    direction=DIR_BULL,
                    kind=ZONE_FVG,
                    mitigated=_mitigated_after(close, i + 2, high[i - 1], DIR_BULL),
                )
            )
        elif high[i + 1] < low[i - 1]:
            zones.append(
                Zone(
                    start_index=i - 1,
                    end_index=i + 1,
                    low=high[i + 1],
                    high=low[i - 1],
                    direction=DIR_BEAR,
                    kind=ZONE_FVG,
                    mitigated=_mitigated_after(close, i + 2, low[i - 1], DIR_BEAR),
                )
            )
    return zones


def _mitigated_after(close: list[float], start: int, level: float, direction: int) -> bool:
    for price in close[start:]:
        if direction == DIR_BULL and price < level:
            return True
        if direction == DIR_BEAR and price > level:
            return True
    return False


def detect_order_blocks(
    open_: list[float],
    high: list[float],
    low: list[float],
    close: list[float],
    events: list[Event],
    lookback: int = 15,
) -> list[Zone]:
    n = len(close)
    zones: list[Zone] = []
    seen: set[int] = set()
    for event in events:
        start = max(0, event.index - lookback)
        ob = -1
        if event.direction == DIR_BULL:
            for i in range(event.index - 1, start - 1, -1):
                if close[i] < open_[i]:
                    ob = i
                    break
        else:
            for i in range(event.index - 1, start - 1, -1):
                if close[i] > open_[i]:
                    ob = i
                    break
        if ob < 0 or ob in seen:
            continue
        seen.add(ob)
        mitigated = False
        if ob + 1 < n:
            if event.direction == DIR_BULL:
                mitigated = _mitigated_after(close, ob + 1, low[ob], DIR_BULL)
            else:
                mitigated = _mitigated_after(close, ob + 1, high[ob], DIR_BEAR)
        zones.append(
            Zone(
                start_index=ob,
                end_index=ob,
                low=low[ob],
                high=high[ob],
                direction=event.direction,
                kind=ZONE_OB,
                mitigated=mitigated,
            )
        )
    return zones


def infer_bias(high: list[float], low: list[float], close: list[float], events: list[Event]) -> int:
    if events:
        return events[-1].direction
    lookback = 10
    n = len(close)
    if n < lookback + 1:
        return DIR_NONE
    last = n - 1
    prev = n - lookback - 1
    if high[last] > high[prev] and low[last] >= low[prev]:
        return DIR_BULL
    if low[last] < low[prev] and high[last] <= high[prev]:
        return DIR_BEAR
    if close[last] > close[prev]:
        return DIR_BULL
    if close[last] < close[prev]:
        return DIR_BEAR
    return DIR_NONE


def analyze(
    open_: list[float],
    high: list[float],
    low: list[float],
    close: list[float],
    left: int = 2,
    right: int = 2,
) -> Snapshot:
    events = detect_structure(open_, high, low, close, left, right)
    sweeps, equal_pools = detect_sweeps(high, low, close, left, right)
    return Snapshot(
        bias=infer_bias(high, low, close, events),
        events=events,
        sweeps=sweeps,
        fvgs=detect_fvg(high, low, close),
        obs=detect_order_blocks(open_, high, low, close, events),
        equal_pools=equal_pools,
    )


def kind_name(kind: int) -> str:
    return {KIND_BOS: "BOS", KIND_CHOCH: "CHoCH", KIND_MSS: "MSS"}.get(kind, "?")


def dir_name(direction: int) -> str:
    if direction == DIR_BULL:
        return "BULL"
    if direction == DIR_BEAR:
        return "BEAR"
    return "FLAT"


def zone_name(kind: int) -> str:
    return "FVG" if kind == ZONE_FVG else "Order Block"


def chat_lines(symbol: str, snap: Snapshot) -> list[str]:
    """Text block shown on the MT5 chart chat / Comment panel."""
    lines = [f"{symbol}  bias {dir_name(snap.bias)}"]
    for kind, label in ((KIND_BOS, "BOS"), (KIND_CHOCH, "CHoCH"), (KIND_MSS, "MSS")):
        event = snap.last_of(kind)
        if event is None:
            lines.append(f"  {label}: none")
        else:
            lines.append(f"  {label}: {dir_name(event.direction)} @ {event.broken:.5f}")
    sweep = snap.last_sweep()
    if sweep is None:
        lines.append("  Liquidity sweep: none")
    else:
        side = "SSL" if sweep.direction == DIR_BULL else "BSL"
        lines.append(f"  Liquidity sweep: {side} {dir_name(sweep.direction)}")
    extra = snap.last_sweep(equal_extra=True)
    if extra is None:
        lines.append("  Equal-liquidity sweep extra: none")
    else:
        lines.append(
            f"  Equal-liquidity sweep extra: {dir_name(extra.direction)} "
            f"({extra.members} equals)"
        )
    ob = snap.last_zone(ZONE_OB)
    if ob is None:
        lines.append("  Order Block: none")
    else:
        lines.append(f"  Order Block: {dir_name(ob.direction)} {ob.low:.5f}-{ob.high:.5f}")
    fvg = snap.last_zone(ZONE_FVG)
    if fvg is None:
        lines.append("  FVG: none")
    else:
        lines.append(f"  FVG: {dir_name(fvg.direction)} {fvg.low:.5f}-{fvg.high:.5f}")
    return lines


V75_ALIASES = (
    "Volatility 75 Index",
    "Volatility 75",
    "Vol 75 Index",
    "VOL75",
    "V75",
    "R_75",
    "Volatility75",
    "Volatility_75_Index",
)

V50_1S_ALIASES = (
    "Volatility 50 (1s) Index",
    "Volatility 50 (1s)",
    "Volatility 50 Index 1s",
    "Volatility 50 1s Index",
    "1HZ50V",
    "VOL50_1s",
    "V50_1s",
    "Vol 50 1s",
)


def normalize_symbol_key(name: str) -> str:
    return "".join(ch.lower() for ch in name if ch.isalnum())


def classify_symbol(name: str) -> str | None:
    key = normalize_symbol_key(name)
    if "1hz50" in key or ("vol" in key and "50" in key and "1s" in key):
        return "v50_1s"
    if key in {"r75", "vol75", "v75"} or ("vol" in key and "75" in key and "1s" not in key and "1hz" not in key):
        return "v75"
    return None


def resolve_from_market(requested: str, available: list[str], which: str) -> str | None:
    wanted = {normalize_symbol_key(a) for a in (V75_ALIASES if which == "v75" else V50_1S_ALIASES)}
    wanted.add(normalize_symbol_key(requested))
    available_keys = {normalize_symbol_key(s): s for s in available}
    for key in wanted:
        if key in available_keys:
            return available_keys[key]
    if requested in available:
        return requested
    for symbol in available:
        if classify_symbol(symbol) == which:
            return symbol
    return None
