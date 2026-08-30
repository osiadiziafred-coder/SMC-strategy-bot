"""Central configuration for the ML/SMC trading robot.

All tunable parameters live here so the brain, trainer, risk manager and command
bridge stay in sync. Values can be overridden with environment variables (see
:func:`Config.from_env`) which is convenient for deployment without editing code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DEFAULT_MODEL_DIR = PACKAGE_DIR / "models"
DEFAULT_LOG_DIR = PACKAGE_DIR / "logs"

# For offline testing the bridge lives inside the project. In production this
# MUST point at the MetaTrader 5 terminal's shared folder, i.e.
# ``<MT5 data folder>\\MQL5\\Files\\smc_bridge`` when the EA uses local files, or
# the terminal *Common* folder ``...\\Terminal\\Common\\Files\\smc_bridge`` when
# the EA opens files with FILE_COMMON (the default in the shipped EA).
DEFAULT_BRIDGE_DIR = PROJECT_DIR / "smc_bridge"


@dataclass
class Config:
    # --- Market -----------------------------------------------------------
    symbol: str = "XAUUSDm"
    # Timeframe roles. Names map to MetaTrader5 constants in mt5_connector.
    bias_timeframe: str = "H1"        # major market bias
    confirm_timeframe: str = "M30"    # structure confirmation
    entry_timeframe: str = "M15"      # entry / setup timeframe

    # Number of bars to request per timeframe when analysing live.
    live_bars: int = 400
    # Number of bars to pull per timeframe when training.
    train_bars: int = 20_000

    # --- Machine learning -------------------------------------------------
    # Preferred model backend, tried in order until one is importable.
    model_backends: tuple[str, ...] = ("lightgbm", "xgboost", "random_forest")
    ml_min_confidence: float = 0.70   # ML_MIN_CONFIDENCE
    model_dir: Path = field(default_factory=lambda: DEFAULT_MODEL_DIR)
    model_filename: str = "smc_xauusd_model.joblib"

    # Label engineering (triple-barrier). SL distance = atr * atr_sl_mult.
    label_horizon: int = 16           # bars ahead to resolve TP/SL
    atr_period: int = 14
    atr_sl_mult: float = 1.5          # SL distance in ATRs used for labelling

    # --- Risk / trade management -----------------------------------------
    risk_reward: float = 2.0          # 1:2
    max_open_positions: int = 1
    # Lot sizing rule: lot = balance / lot_per_balance * lot_unit.
    lot_per_balance: float = 100.0
    lot_unit: float = 0.01
    # Broker volume constraints (overridden by live symbol info when available).
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01

    breakeven_r: float = 1.0          # move SL to BE at +1R
    breakeven_buffer_points: float = 20.0
    trail_start_r: float = 1.5        # activate trailing at +1.5R
    trail_distance_atr: float = 1.0   # trailing distance in ATRs
    trail_enabled: bool = True

    # --- Safety gates -----------------------------------------------------
    max_spread_points: float = 60.0   # reject if spread wider than this
    min_sl_distance_points: float = 50.0
    point: float = 0.01               # XAUUSD price increment (fallback)

    # --- Bridge / heartbeat ----------------------------------------------
    bridge_dir: Path = field(default_factory=lambda: DEFAULT_BRIDGE_DIR)
    command_filename: str = "command.json"
    status_filename: str = "status.json"
    heartbeat_interval_sec: float = 5.0
    python_timeout_sec: float = 30.0  # EA rejects entries if PY stale longer
    poll_interval_sec: float = 2.0    # brain live-loop cadence

    # --- Data source ------------------------------------------------------
    # "mt5" (live terminal), "synthetic" (offline generator) or "csv".
    data_source: str = "mt5"
    csv_dir: Path = field(default_factory=lambda: PROJECT_DIR / "data")

    # --- Logging ----------------------------------------------------------
    log_dir: Path = field(default_factory=lambda: DEFAULT_LOG_DIR)
    log_level: str = "INFO"

    @property
    def model_path(self) -> Path:
        return self.model_dir / self.model_filename

    @property
    def command_path(self) -> Path:
        return self.bridge_dir / self.command_filename

    @property
    def status_path(self) -> Path:
        return self.bridge_dir / self.status_filename

    @property
    def timeframes(self) -> list[str]:
        return [self.bias_timeframe, self.confirm_timeframe, self.entry_timeframe]

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
    def from_env(cls, **overrides) -> "Config":
        """Build a config, applying environment-variable overrides.

        Environment variables are prefixed with ``SMC_`` and upper-cased, e.g.
        ``SMC_ML_MIN_CONFIDENCE=0.8`` or ``SMC_DATA_SOURCE=synthetic``.
        """

        cfg = cls(**overrides)
        for f in cfg.__dataclass_fields__.values():  # type: ignore[attr-defined]
            env_key = f"SMC_{f.name.upper()}"
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
                else:
                    setattr(cfg, f.name, raw)
            except (TypeError, ValueError):
                # Ignore malformed overrides and keep the default.
                pass
        return cfg


# A shared default instance for simple imports.
CONFIG = Config()
