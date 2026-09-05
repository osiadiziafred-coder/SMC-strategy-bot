"""Per-instrument configuration for the ML trend/pullback scalper.

Three instruments ship with independent models, thresholds, lot rules and
volatility gates:

* Volatility 50 (1s) Index
* Volatility 75 Index
* XAUUSD

Environment overrides use the ``SCALP_`` prefix, e.g. ``SCALP_SYMBOL=XAUUSD``.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DEFAULT_MODEL_DIR = PACKAGE_DIR / "models"
DEFAULT_LOG_DIR = PACKAGE_DIR / "logs"
DEFAULT_BRIDGE_DIR = PROJECT_DIR / "ml_scalper_bridge"

# ---------------------------------------------------------------------------
# Instrument presets
# ---------------------------------------------------------------------------
# ``start_price`` / ``vol`` / ``spread_range`` are used only by the offline
# synthetic feed. Lot/point/digits are broker facts; a live MT5 terminal
# overrides them from symbol_info.
#
# Volatility 50 (1s) is analysed on M15/M5 with optional M1 precision. The
# model is never allowed to depend on M1 alone — the 1-second feed is too
# noisy for a standalone signal.
INSTRUMENTS: dict[str, dict] = {
    "Volatility 50 (1s) Index": {
        "aliases": (
            "Volatility 50 (1s)",
            "Volatility 50 Index",
            "V50",
            "V50_1s",
            "VOL50",
        ),
        "slug": "v50_1s",
        "start_price": 8_500.0,
        "vol": 0.0016,
        "spread_range": (12.0, 40.0),
        "point": 0.01,
        "digits": 2,
        "min_lot": 0.001,
        "lot_step": 0.001,
        "max_lot": 50.0,
        "contract_size": 1.0,
        "lot_unit": 0.001,
        "lot_per_balance": 100.0,
        "max_spread_points": 80.0,
        "min_sl_distance_points": 80.0,
        "atr_sl_mult": 1.2,
        "label_horizon": 8,
        "ml_min_confidence": 0.70,
        "min_outcome_prob": 0.55,
        "use_m1_precision": True,
        "require_m1_confirm": False,  # never a hard gate on the 1s index
        "poll_interval_sec": 1.0,
        "max_daily_loss_pct": 3.0,
        "max_consecutive_losses": 4,
        "abnormal_atr_mult": 3.0,
        "max_spread_vs_median": 2.0,
        "session_vwap": False,  # 24/7 synthetic — rolling VWAP
        "vwap_window": 96,  # M5 bars ≈ 8 hours
        "breakeven_buffer_points": 20.0,
        "trail_distance_atr": 1.0,
        "leverage": 200.0,
    },
    "Volatility 75 Index": {
        "aliases": (
            "Volatility 75",
            "V75",
            "VOL75",
            "R_75",
        ),
        "slug": "v75",
        "start_price": 100_000.0,
        "vol": 0.0020,
        "spread_range": (20.0, 60.0),
        "point": 0.01,
        "digits": 2,
        "min_lot": 0.001,
        "lot_step": 0.001,
        "max_lot": 50.0,
        "contract_size": 1.0,
        "lot_unit": 0.001,
        "lot_per_balance": 100.0,
        "max_spread_points": 80.0,
        "min_sl_distance_points": 100.0,
        "atr_sl_mult": 1.5,
        "label_horizon": 12,
        "ml_min_confidence": 0.70,
        "min_outcome_prob": 0.55,
        "use_m1_precision": True,
        "require_m1_confirm": False,
        "poll_interval_sec": 2.0,
        "max_daily_loss_pct": 3.0,
        "max_consecutive_losses": 3,
        "abnormal_atr_mult": 2.8,
        "max_spread_vs_median": 2.0,
        "session_vwap": False,
        "vwap_window": 96,
        "breakeven_buffer_points": 30.0,
        "trail_distance_atr": 1.0,
        "leverage": 200.0,
    },
    "XAUUSD": {
        "aliases": (
            "XAUUSDm",
            "XAUUSD.m",
            "GOLD",
            "Gold",
        ),
        "slug": "xauusd",
        "start_price": 2_350.0,
        "vol": 0.0011,
        "spread_range": (18.0, 42.0),
        "point": 0.01,
        "digits": 2,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
        "contract_size": 100.0,
        "lot_unit": 0.01,
        "lot_per_balance": 100.0,
        "max_spread_points": 45.0,
        "min_sl_distance_points": 50.0,
        "atr_sl_mult": 1.2,
        "label_horizon": 16,
        "ml_min_confidence": 0.70,
        "min_outcome_prob": 0.55,
        "use_m1_precision": True,
        "require_m1_confirm": False,
        "poll_interval_sec": 2.0,
        "max_daily_loss_pct": 2.5,
        "max_consecutive_losses": 3,
        "abnormal_atr_mult": 2.5,
        "max_spread_vs_median": 1.6,  # gold execution quality matters
        "session_vwap": True,
        "vwap_window": 96,
        "breakeven_buffer_points": 20.0,
        "trail_distance_atr": 1.0,
        "leverage": 100.0,
    },
}

CANONICAL_SYMBOLS = tuple(INSTRUMENTS.keys())


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def resolve_symbol(name: str) -> str:
    """Map a broker/alias symbol onto a canonical instrument name."""

    raw = (name or "").strip()
    if raw in INSTRUMENTS:
        return raw
    target = _norm(raw)
    for canon, spec in INSTRUMENTS.items():
        candidates = [_norm(canon), *( _norm(a) for a in spec["aliases"] )]
        if target in candidates:
            return canon
    return raw


def instrument_slug(symbol: str) -> str:
    canon = resolve_symbol(symbol)
    spec = INSTRUMENTS.get(canon)
    if spec:
        return spec["slug"]
    return re.sub(r"[^a-z0-9]+", "_", canon.lower()).strip("_") or "custom"


@dataclass
class Config:
    # --- Market -----------------------------------------------------------
    symbol: str = "Volatility 75 Index"
    regime_timeframe: str = "M15"   # market / trend regime
    setup_timeframe: str = "M5"     # primary scalping setup
    entry_timeframe: str = "M1"     # optional precision only

    live_bars: int = 500
    train_bars: int = 12_000        # bars on the M5 setup timeframe

    # --- Machine learning -------------------------------------------------
    model_backends: tuple[str, ...] = ("lightgbm", "xgboost", "random_forest")
    n_estimators: int = 300
    ml_min_confidence: float = 0.70
    min_outcome_prob: float = 0.55
    model_dir: Path = field(default_factory=lambda: DEFAULT_MODEL_DIR)
    model_filename: str = ""        # filled from symbol slug in __post_init__

    label_horizon: int = 12         # M5 bars to resolve TP vs SL
    atr_period: int = 14
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    atr_sl_mult: float = 1.5
    vwap_window: int = 96
    session_vwap: bool = False
    use_m1_precision: bool = True
    require_m1_confirm: bool = False

    # --- Risk / trade management -----------------------------------------
    risk_reward: float = 2.0        # 1:2 minimum
    max_open_positions: int = 1
    lot_per_balance: float = 100.0
    lot_unit: float = 0.001
    min_lot: float = 0.001
    max_lot: float = 50.0
    lot_step: float = 0.001
    leverage: float = 200.0

    breakeven_r: float = 1.0
    breakeven_buffer_points: float = 20.0
    trail_start_r: float = 1.5
    trail_distance_atr: float = 1.0
    trail_enabled: bool = True

    max_daily_loss_pct: float = 3.0
    max_consecutive_losses: int = 3
    max_trades_per_day: int = 40    # multiple trades/day allowed; this is a cap
    abnormal_atr_mult: float = 2.8
    max_spread_vs_median: float = 2.0
    min_margin_level_pct: float = 200.0

    # --- Safety gates -----------------------------------------------------
    max_spread_points: float = 80.0
    min_sl_distance_points: float = 100.0
    point: float = 0.01
    digits: int = 2

    # --- Technical filter tightness --------------------------------------
    pullback_atr_min: float = 0.20  # min retracement depth (ATR)
    pullback_atr_max: float = 2.2
    near_ma_atr: float = 1.15       # price near EMA/VWAP
    min_trend_strength: float = 0.12

    # --- Bridge / heartbeat ----------------------------------------------
    bridge_dir: Path = field(default_factory=lambda: DEFAULT_BRIDGE_DIR)
    command_filename: str = "command.json"
    status_filename: str = "status.json"
    heartbeat_interval_sec: float = 5.0
    python_timeout_sec: float = 30.0
    poll_interval_sec: float = 2.0
    command_cooldown_sec: float = 180.0

    # --- Data source ------------------------------------------------------
    data_source: str = "mt5"
    csv_dir: Path = field(default_factory=lambda: PROJECT_DIR / "data")

    # --- Logging ----------------------------------------------------------
    log_dir: Path = field(default_factory=lambda: DEFAULT_LOG_DIR)
    log_level: str = "INFO"

    def _apply_broker_facts(self) -> None:
        preset = INSTRUMENTS.get(self.symbol)
        if not preset:
            return
        self.point = preset["point"]
        self.digits = preset["digits"]
        self.min_lot = preset["min_lot"]
        self.lot_step = preset["lot_step"]
        self.max_lot = preset["max_lot"]

    def __post_init__(self) -> None:
        self.symbol = resolve_symbol(self.symbol)
        self._apply_broker_facts()
        if not self.model_filename:
            self.model_filename = f"{instrument_slug(self.symbol)}_scalper.joblib"

    def symbol_preset(self) -> dict:
        return INSTRUMENTS.get(self.symbol, INSTRUMENTS["Volatility 75 Index"])

    @property
    def model_path(self) -> Path:
        return Path(self.model_dir) / self.model_filename

    @property
    def command_path(self) -> Path:
        return Path(self.bridge_dir) / self.command_filename

    @property
    def status_path(self) -> Path:
        return Path(self.bridge_dir) / self.status_filename

    @property
    def timeframes(self) -> list[str]:
        tfs = [self.regime_timeframe, self.setup_timeframe]
        if self.use_m1_precision and self.entry_timeframe not in tfs:
            tfs.append(self.entry_timeframe)
        return tfs

    def ensure_dirs(self) -> None:
        for d in (self.model_dir, self.log_dir, self.bridge_dir):
            Path(d).mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Path):
                d[k] = str(v)
        return d

    @classmethod
    def for_symbol(cls, symbol: str, **overrides) -> "Config":
        """Build a config with that instrument's strategy + broker defaults.

        Explicit ``overrides`` always win over the preset.
        """

        canon = resolve_symbol(symbol)
        preset = INSTRUMENTS.get(canon, {})
        strategy_keys = (
            "lot_unit",
            "lot_per_balance",
            "max_spread_points",
            "min_sl_distance_points",
            "atr_sl_mult",
            "label_horizon",
            "ml_min_confidence",
            "min_outcome_prob",
            "use_m1_precision",
            "require_m1_confirm",
            "poll_interval_sec",
            "max_daily_loss_pct",
            "max_consecutive_losses",
            "abnormal_atr_mult",
            "max_spread_vs_median",
            "session_vwap",
            "vwap_window",
            "breakeven_buffer_points",
            "trail_distance_atr",
            "leverage",
        )
        kwargs: dict = {"symbol": canon}
        for key in strategy_keys:
            if key in preset:
                kwargs[key] = preset[key]
        kwargs.update(overrides)
        return cls(**kwargs)

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        symbol = overrides.get("symbol") or os.environ.get("SCALP_SYMBOL", "Volatility 75 Index")
        cfg = cls.for_symbol(symbol, **{k: v for k, v in overrides.items() if k != "symbol"})
        for f in fields(cfg):
            env_key = f"SCALP_{f.name.upper()}"
            if env_key not in os.environ:
                continue
            raw = os.environ[env_key]
            current = getattr(cfg, f.name)
            try:
                if isinstance(current, bool):
                    setattr(cfg, f.name, raw.strip().lower() in {"1", "true", "yes", "on"})
                elif isinstance(current, int):
                    setattr(cfg, f.name, int(raw))
                elif isinstance(current, float):
                    setattr(cfg, f.name, float(raw))
                elif isinstance(current, Path):
                    setattr(cfg, f.name, Path(raw))
                elif isinstance(current, tuple):
                    setattr(cfg, f.name, tuple(x.strip() for x in raw.split(",") if x.strip()))
                else:
                    setattr(cfg, f.name, raw)
            except (TypeError, ValueError):
                pass
        cfg.symbol = resolve_symbol(cfg.symbol)
        cfg._apply_broker_facts()
        return cfg


CONFIG = Config()
