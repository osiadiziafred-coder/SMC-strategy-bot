"""Configuration for the SMC XAUUSDm trading robot."""

from dataclasses import dataclass, field
from enum import Enum


class Timeframe(Enum):
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"


# MetaTrader 5 timeframe constants (set at runtime when MT5 is available)
MT5_TIMEFRAMES = {
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.H1: 60,
}


@dataclass
class Config:
    # Instrument
    symbol: str = "XAUUSDm"

    # Timeframes
    bias_tf: Timeframe = Timeframe.H1
    structure_tf: Timeframe = Timeframe.M15
    entry_tf: Timeframe = Timeframe.M5

    # Risk / reward
    risk_reward_ratio: float = 2.0
    breakeven_at_r: float = 1.0  # Move SL to breakeven when price reaches 1R

    # Position sizing: every $100 balance = 0.01 lot
    balance_per_001_lot: float = 100.0
    min_lot: float = 0.01
    max_lot: float = 100.0

    # Trade limits
    max_open_positions: int = 1
    trade_during_news: bool = True

    # SMC detection parameters
    swing_lookback: int = 5          # bars each side for swing detection
    sweep_tolerance_pips: float = 2.0  # how far past swing wick counts as sweep
    fvg_min_gap_pips: float = 1.0    # minimum gap size for valid FVG
    structure_lookback: int = 50     # bars to scan for structure
    liquidity_lookback: int = 30     # bars to find swing liquidity pools

    # Loop timing
    scan_interval_seconds: int = 10
    candle_bars_h1: int = 200
    candle_bars_m15: int = 300
    candle_bars_m5: int = 500

    # MT5 connection (override via environment or edit here)
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = ""
    mt5_path: str = ""  # e.g. "C:/Program Files/MetaTrader 5/terminal64.exe"

    # Logging
    log_level: str = "INFO"
    log_file: str = "smc_robot.log"

    # Pip size for XAUUSD (1 pip = 0.1 for most brokers on gold)
    pip_size: float = 0.1

    def lot_size_for_balance(self, balance: float) -> float:
        """Calculate lot size: $100 = 0.01 lot."""
        lots = (balance / self.balance_per_001_lot) * 0.01
        lots = round(lots, 2)
        return max(self.min_lot, min(lots, self.max_lot))


DEFAULT_CONFIG = Config()
