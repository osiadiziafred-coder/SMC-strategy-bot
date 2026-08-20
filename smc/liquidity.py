"""Liquidity sweep detection."""

from dataclasses import dataclass

import pandas as pd

from smc.swing import SwingPoint, find_swing_highs, find_swing_lows, recent_swing


@dataclass
class LiquiditySweep:
  direction: str  # "bullish" (swept lows) or "bearish" (swept highs)
  sweep_index: int
  sweep_price: float
  swept_level: float
  sweep_time: pd.Timestamp


def detect_liquidity_sweep(
  df: pd.DataFrame,
  lookback: int = 30,
  swing_lookback: int = 5,
  tolerance_pips: float = 2.0,
  pip_size: float = 0.1,
) -> LiquiditySweep | None:
  """
  Detect if the most recent price action swept liquidity and reversed.

  Bullish sweep: price breaks below a swing low then closes back above it.
  Bearish sweep: price breaks above a swing high then closes back below it.
  """
  if len(df) < lookback + swing_lookback * 2:
    return None

  tolerance = tolerance_pips * pip_size
  scan_df = df.iloc[-lookback:]
  offset = len(df) - lookback

  swing_highs = find_swing_highs(scan_df, swing_lookback)
  swing_lows = find_swing_lows(scan_df, swing_lookback)

  # Check last few candles for sweep
  for i in range(len(scan_df) - 1, max(len(scan_df) - 5, 0), -1):
    candle = scan_df.iloc[i]
    abs_index = offset + i

    # Bullish sweep: wick below swing low, close back above
    prior_lows = [s for s in swing_lows if s.index < i]
    if prior_lows:
      target_low = prior_lows[-1]
      if candle["low"] < target_low.price - tolerance and candle["close"] > target_low.price:
        return LiquiditySweep(
          direction="bullish",
          sweep_index=abs_index,
          sweep_price=candle["low"],
          swept_level=target_low.price,
          sweep_time=scan_df.index[i],
        )

    # Bearish sweep: wick above swing high, close back below
    prior_highs = [s for s in swing_highs if s.index < i]
    if prior_highs:
      target_high = prior_highs[-1]
      if candle["high"] > target_high.price + tolerance and candle["close"] < target_high.price:
        return LiquiditySweep(
          direction="bearish",
          sweep_index=abs_index,
          sweep_price=candle["high"],
          swept_level=target_high.price,
          sweep_time=scan_df.index[i],
        )

  return None
