from __future__ import annotations

from dataclasses import dataclass


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


def lots_from_balance(
    balance: float,
    spec: SymbolSpec,
    balance_per_step: float = 100.0,
    lot_per_step: float = 0.01,
) -> float:
    """Every $100 of balance adds 0.01 lots, then snap to broker min/step/max.

    $100 -> 0.01, $200 -> 0.02, $500 -> 0.05, $1,000 -> 0.10
    Partial hundreds do not round up: $199 -> 0.01
    """
    if balance < balance_per_step or spec.volume_step <= 0:
        return 0.0
    raw = int(balance // balance_per_step) * lot_per_step
    steps = round(raw / spec.volume_step)
    lots = steps * spec.volume_step
    lots = max(spec.volume_min, min(spec.volume_max, lots))
    lots = round(lots / spec.volume_step) * spec.volume_step
    precision = max(0, len(str(spec.volume_step).split(".")[-1]) if "." in str(spec.volume_step) else 0)
    lots = round(lots, precision)
    if lots < spec.volume_min:
        return 0.0
    return lots


def normalize_lots(lots: float, spec: SymbolSpec) -> float:
    if spec.volume_step <= 0:
        return 0.0
    steps = round(lots / spec.volume_step)
    value = steps * spec.volume_step
    value = max(spec.volume_min, min(spec.volume_max, value))
    precision = max(0, len(str(spec.volume_step).split(".")[-1]) if "." in str(spec.volume_step) else 0)
    return round(value, precision)
