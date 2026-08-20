"""Market Structure Shift (MSS) / Change of Character (CHoCH) detection."""

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from smc.swing import find_swing_highs, find_swing_lows


class Bias(str, Enum):
  BULLISH = "bullish"
  BEARISH = "bearish"
  NEUTRAL = "neutral"


@dataclass
class StructureShift:
  direction: str  # "bullish" or "bearish"
  shift_index: int
  break_level: float
  shift_time: pd.Timestamp


def detect_structure_shift(
  df: pd.DataFrame,
  after_index: int = 0,
  swing_lookback: int = 5,
  lookback: int = 50,
) -> StructureShift | None:
  """
  Detect MSS/CHoCH after a given index.

  Bullish CHoCH: price breaks above the most recent swing high after a sweep low.
  Bearish CHoCH: price breaks below the most recent swing low after a sweep high.
  """
  if len(df) < lookback:
    return None

  scan_df = df.iloc[-lookback:]
  offset = len(df) - lookback

  swing_highs = find_swing_highs(scan_df, swing_lookback)
  swing_lows = find_swing_lows(scan_df, swing_lookback)

  # Scan candles after the sweep for structure break
  rel_after = max(0, after_index - offset)

  for i in range(rel_after, len(scan_df)):
    candle = scan_df.iloc[i]
    abs_index = offset + i

    # Bullish: break above recent swing high
    prior_highs = [s for s in swing_highs if s.index < i]
    if prior_highs:
      last_high = prior_highs[-1]
      if candle["close"] > last_high.price and scan_df.iloc[i - 1]["close"] <= last_high.price:
        return StructureShift(
          direction="bullish",
          shift_index=abs_index,
          break_level=last_high.price,
          shift_time=scan_df.index[i],
        )

    # Bearish: break below recent swing low
    prior_lows = [s for s in swing_lows if s.index < i]
    if prior_lows:
      last_low = prior_lows[-1]
      if candle["close"] < last_low.price and scan_df.iloc[i - 1]["close"] >= last_low.price:
        return StructureShift(
          direction="bearish",
          shift_index=abs_index,
          break_level=last_low.price,
          shift_time=scan_df.index[i],
        )

  return None


def determine_bias(df: pd.DataFrame, swing_lookback: int = 5) -> Bias:
  """Simple H1 bias from the last two swing highs and lows (HH/HL or LH/LL)."""
  swing_highs = find_swing_highs(df, swing_lookback)
  swing_lows = find_swing_lows(df, swing_lookback)

  if len(swing_highs) < 2 or len(swing_lows) < 2:
    return Bias.NEUTRAL

  hh = swing_highs[-1].price > swing_highs[-2].price
  hl = swing_lows[-1].price > swing_lows[-2].price
  lh = swing_highs[-1].price < swing_highs[-2].price
  ll = swing_lows[-1].price < swing_lows[-2].price

  if hh and hl:
    return Bias.BULLISH
  if lh and ll:
    return Bias.BEARISH
  return Bias.NEUTRAL
