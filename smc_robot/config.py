from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class TimeframeConfig(BaseModel):
    bias: str = "H1"
    confirm: str = "M30"
    entry: str = "M15"


class BarsConfig(BaseModel):
    h1: int = 300
    m30: int = 400
    m15: int = 500


class SmcConfig(BaseModel):
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
    displacement_body_atr: float = 1.10
    discount_max: float = 0.50
    premium_min: float = 0.50
    require_premium_discount: bool = False


class ScoringWeights(BaseModel):
    h1_aligned: float = 20.0
    m30_confirmation: float = 15.0
    liquidity_sweep: float = 15.0
    equal_liquidity_extra: float = 5.0
    order_block: float = 15.0
    fvg: float = 10.0
    bos: float = 5.0
    choch: float = 5.0
    mss: float = 10.0
    good_conditions: float = 10.0
    poor_conditions: float = -20.0
    h1_conflict: float = -25.0
    premium_discount: float = 5.0
    displacement: float = 5.0


class ScoringConfig(BaseModel):
    min_score: float = 70.0
    use_ml: bool = True
    require_ml: bool = False
    ml_blend: float = 0.40
    ml_min_probability: float = 0.60
    model_path: str = "models/smc_scorer.joblib"
    allowed_grades: list[str] = Field(default_factory=lambda: ["A+", "A"])
    weights: ScoringWeights = Field(default_factory=ScoringWeights)


class RiskConfig(BaseModel):
    sizing_mode: str = "percent"
    risk_percent: float = 0.50
    reward_ratio: float = 2.0
    balance_per_lot_step: float = 100.0
    lot_step_per_balance: float = 0.01
    sl_buffer_atr_mult: float = 0.10
    breakeven_r: float = 1.0
    breakeven_buffer_points: float = 0.0
    trail_start_r: float = 1.5
    trail_enabled: bool = True
    max_positions: int = 1
    max_lot: float = 5.0
    min_lot: float = 0.01
    magic: int = 20250824
    comment: str = "SMC-AI"


class DailyRiskConfig(BaseModel):
    max_daily_loss_percent: float = 3.0
    max_daily_profit_percent: float = 0.0
    max_trades_per_day: int = 8
    max_consecutive_losses: int = 3


class CooldownConfig(BaseModel):
    bars_after_close: int = 2
    bars_after_loss: int = 4
    stronger_after_loss: bool = True
    loss_min_grade: str = "A+"
    loss_ml_boost: float = 0.08


class SessionConfig(BaseModel):
    enabled: bool = False
    allowed: list[str] = Field(
        default_factory=lambda: ["ASIAN", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"]
    )
    asian: tuple[int, int] = (0, 8)
    london: tuple[int, int] = (7, 16)
    new_york: tuple[int, int] = (12, 21)


class NewsConfig(BaseModel):
    mode: str = "allow"
    calendar_path: str = "config/news_calendar.csv"
    minutes_before: int = 30
    minutes_after: int = 30
    high_impact_only: bool = True


class ProtectionConfig(BaseModel):
    max_spread_points: float = 80.0
    max_slippage_points: float = 40.0
    max_quote_age_ms: int = 3000
    spread_spike_mult: float = 2.5
    spread_window: int = 20
    min_stop_points: float = 50.0
    require_margin: bool = True


class MarketConditionsConfig(BaseModel):
    atr_slow_period: int = 50
    low_atr_ratio: float = 0.60
    high_atr_ratio: float = 2.20
    choppy_efficiency: float = 0.18


class BridgeConfig(BaseModel):
    directory: str = "logs/smc_bridge"
    command_file: str = "command.json"
    status_file: str = "status.json"
    heartbeat_seconds: int = 10


class RobotConfig(BaseModel):
    poll_seconds: int = 5
    analyze_on_closed_bar_only: bool = True
    log_dir: str = "logs"
    fail_closed: bool = True


class Settings(BaseModel):
    symbol: str = "XAUUSDm"
    timeframes: TimeframeConfig = Field(default_factory=TimeframeConfig)
    bars: BarsConfig = Field(default_factory=BarsConfig)
    smc: SmcConfig = Field(default_factory=SmcConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    daily_risk: DailyRiskConfig = Field(default_factory=DailyRiskConfig)
    cooldown: CooldownConfig = Field(default_factory=CooldownConfig)
    sessions: SessionConfig = Field(default_factory=SessionConfig)
    news: NewsConfig = Field(default_factory=NewsConfig)
    protection: ProtectionConfig = Field(default_factory=ProtectionConfig)
    market_conditions: MarketConditionsConfig = Field(default_factory=MarketConditionsConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    robot: RobotConfig = Field(default_factory=RobotConfig)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Optional[str | Path] = None) -> Settings:
    data: dict[str, Any] = {}
    default_path = Path(__file__).resolve().parent.parent / "config" / "default.yaml"
    if default_path.exists():
        with default_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    if path is not None:
        custom = Path(path)
        if custom.exists():
            with custom.open("r", encoding="utf-8") as handle:
                data = _deep_merge(data, yaml.safe_load(handle) or {})
    return Settings.model_validate(data)
