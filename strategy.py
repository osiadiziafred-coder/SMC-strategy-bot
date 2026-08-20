"""Multi-timeframe SMC strategy engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from config import Config
from smc.fvg import find_fvgs, nearest_fvg
from smc.liquidity import detect_liquidity_sweep
from smc.structure import Bias, determine_bias, detect_structure_shift

logger = logging.getLogger(__name__)


@dataclass
class Signal:
  direction: str  # "buy" or "sell"
  entry_price: float
  sl_price: float
  reason: str
  bias: str
  sweep_level: float
  fvg_zone: tuple[float, float] | None = None


class SMCStrategy:
  """
  Multi-timeframe SMC confluence strategy.

  H1  → directional bias
  M15 → liquidity sweep + MSS/CHoCH
  M5  → FVG retest entry
  """

  def __init__(self, config: Config) -> None:
    self.config = config

  def analyze(
    self,
    df_h1: pd.DataFrame,
    df_m15: pd.DataFrame,
    df_m5: pd.DataFrame,
  ) -> Signal | None:
    if df_h1.empty or df_m15.empty or df_m5.empty:
      logger.debug("Insufficient candle data")
      return None

    # Step 1: H1 bias
    bias = determine_bias(df_h1, self.config.swing_lookback)
    if bias == Bias.NEUTRAL:
      logger.debug("H1 bias is neutral — no trade")
      return None

    logger.debug("H1 bias: %s", bias.value)

    # Step 2: M15 liquidity sweep
    sweep = detect_liquidity_sweep(
      df_m15,
      lookback=self.config.liquidity_lookback,
      swing_lookback=self.config.swing_lookback,
      tolerance_pips=self.config.sweep_tolerance_pips,
      pip_size=self.config.pip_size,
    )
    if sweep is None:
      logger.debug("No liquidity sweep on M15")
      return None

    # Sweep direction must align with H1 bias
    if bias == Bias.BULLISH and sweep.direction != "bullish":
      logger.debug("Sweep direction (%s) conflicts with bullish bias", sweep.direction)
      return None
    if bias == Bias.BEARISH and sweep.direction != "bearish":
      logger.debug("Sweep direction (%s) conflicts with bearish bias", sweep.direction)
      return None

    logger.info(
      "M15 %s liquidity sweep at %.2f (level %.2f)",
      sweep.direction,
      sweep.sweep_price,
      sweep.swept_level,
    )

    # Step 3: M15 MSS/CHoCH after sweep
    shift = detect_structure_shift(
      df_m15,
      after_index=sweep.sweep_index,
      swing_lookback=self.config.swing_lookback,
      lookback=self.config.structure_lookback,
    )
    if shift is None:
      logger.debug("No MSS/CHoCH after sweep on M15")
      return None

    if shift.direction != sweep.direction:
      logger.debug("Structure shift direction mismatch")
      return None

    logger.info("M15 %s CHoCH at %.2f", shift.direction, shift.break_level)

    # Step 4: M5 FVG entry
    fvgs = find_fvgs(
      df_m5,
      min_gap_pips=self.config.fvg_min_gap_pips,
      pip_size=self.config.pip_size,
      after_index=max(0, len(df_m5) - 50),
    )

    current_price = df_m5["close"].iloc[-1]
    fvg = nearest_fvg(fvgs, shift.direction, current_price, after_index=0)

    if fvg is None:
      logger.debug("No valid FVG on M5 for entry")
      return None

    logger.info(
      "M5 %s FVG zone [%.2f – %.2f], price %.2f",
      fvg.direction,
      fvg.bottom,
      fvg.top,
      current_price,
    )

    # Build signal
    if shift.direction == "bullish":
      direction = "buy"
      entry_price = current_price
      sl_price = sweep.sweep_price - self.config.pip_size  # below sweep wick
    else:
      direction = "sell"
      entry_price = current_price
      sl_price = sweep.sweep_price + self.config.pip_size  # above sweep wick

    reason = (
      f"H1 {bias.value} bias | M15 {sweep.direction} sweep + CHoCH | "
      f"M5 FVG retest [{fvg.bottom:.2f}-{fvg.top:.2f}]"
    )

    return Signal(
      direction=direction,
      entry_price=entry_price,
      sl_price=sl_price,
      reason=reason,
      bias=bias.value,
      sweep_level=sweep.swept_level,
      fvg_zone=(fvg.bottom, fvg.top),
    )
