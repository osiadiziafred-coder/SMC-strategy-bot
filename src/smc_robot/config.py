from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_TIMEFRAMES = ("M5", "M15", "H1")


@dataclass(slots=True)
class RobotConfig:
    symbol: str = "XAUUSDc"
    timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES
    htf_bias: str = "H1"
    entry_timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES
    risk_reward: float = 2.0
    max_positions: int = 3
    lot_per_300_usd: float = 0.01
    min_lot: float = 0.01
    lot_step: float = 0.01
    trail_activate_r: float = 1.0
    trail_to_breakeven: bool = True
    breakeven_buffer: float = 0.05
    trail_distance_r: float = 1.0
    swing_length: int = 5
    fvg_min_size: float = 0.20
    ob_lookback: int = 12
    displacement_body_atr: float = 1.2
    min_confluence_score: int = 55
    close_break: bool = True
    trade_news: bool = True
    allow_multiple_trades_per_day: bool = True
    one_position_per_timeframe: bool = True
    max_trades_per_day: int = 24
    magic: int = 20250819
    deviation_points: int = 30
    contract_size: float = 100.0
    point: float = 0.01
    starting_balance: float = 300.0
    spread: float = 0.30

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RobotConfig":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs: dict[str, Any] = {}
        for key, value in data.items():
            if key not in known:
                continue
            if key in {"timeframes", "entry_timeframes"} and value is not None:
                kwargs[key] = tuple(value)
            else:
                kwargs[key] = value
        return cls(**kwargs)


def load_config(path: str | Path | None = None) -> RobotConfig:
    if path is None:
        for candidate in (
            Path("config.yaml"),
            Path(__file__).resolve().parents[2] / "config.yaml",
        ):
            if candidate.exists():
                path = candidate
                break
    if path is None:
        return RobotConfig()
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return RobotConfig.from_dict(raw)
