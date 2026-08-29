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
    tick_size: float = 0.01
    tick_value: float = 1.0
    margin_initial: float = 0.0


def lots_from_balance(
    balance: float,
    spec: SymbolSpec,
    balance_per_step: float = 100.0,
    lot_per_step: float = 0.01,
) -> float:
    """Legacy step sizing: every $100 of balance adds 0.01 lots."""
    if balance < balance_per_step or spec.volume_step <= 0:
        return 0.0
    raw = int(balance // balance_per_step) * lot_per_step
    return normalize_lots(raw, spec)


def lots_from_risk_percent(
    equity: float,
    risk_percent: float,
    sl_distance: float,
    spec: SymbolSpec,
    min_lot: float = 0.01,
    max_lot: float = 5.0,
) -> float:
    """Primary sizing: risk a percent of equity given SL distance and tick value."""
    if equity <= 0 or risk_percent <= 0 or sl_distance <= 0:
        return 0.0
    tick_size = spec.tick_size if spec.tick_size > 0 else spec.point
    tick_value = spec.tick_value if spec.tick_value > 0 else 1.0
    if tick_size <= 0 or tick_value <= 0:
        return 0.0
    risk_amount = equity * (risk_percent / 100.0)
    loss_per_lot = (sl_distance / tick_size) * tick_value
    if loss_per_lot <= 0:
        return 0.0
    raw = risk_amount / loss_per_lot
    lots = normalize_lots(raw, spec)
    lots = max(min_lot, min(max_lot, lots, spec.volume_max))
    lots = normalize_lots(lots, spec)
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
