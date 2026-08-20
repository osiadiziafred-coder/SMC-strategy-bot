"""Fair Value Gap (FVG) detection."""

from dataclasses import dataclass

import pandas as pd


@dataclass
class FairValueGap:
  direction: str  # "bullish" or "bearish"
  top: float
  bottom: float
  index: int
  time: pd.Timestamp

  @property
  def midpoint(self) -> float:
    return (self.top + self.bottom) / 2


def find_fvgs(
  df: pd.DataFrame,
  min_gap_pips: float = 1.0,
  pip_size: float = 0.1,
  after_index: int = 0,
) -> list[FairValueGap]:
  """
  Find Fair Value Gaps in OHLC data.

  Bullish FVG: candle[i-2].high < candle[i].low  (gap up)
  Bearish FVG: candle[i-2].low  > candle[i].high (gap down)
  """
  min_gap = min_gap_pips * pip_size
  fvgs: list[FairValueGap] = []

  for i in range(max(2, after_index), len(df)):
    c0 = df.iloc[i - 2]
    c2 = df.iloc[i]

    # Bullish FVG
    if c2["low"] > c0["high"]:
      gap = c2["low"] - c0["high"]
      if gap >= min_gap:
        fvgs.append(
          FairValueGap(
            direction="bullish",
            top=c2["low"],
            bottom=c0["high"],
            index=i,
            time=df.index[i],
          )
        )

    # Bearish FVG
    if c2["high"] < c0["low"]:
      gap = c0["low"] - c2["high"]
      if gap >= min_gap:
        fvgs.append(
          FairValueGap(
            direction="bearish",
            top=c0["low"],
            bottom=c2["high"],
            index=i,
            time=df.index[i],
          )
        )

  return fvgs


def nearest_fvg(
  fvgs: list[FairValueGap],
  direction: str,
  current_price: float,
  after_index: int = 0,
) -> FairValueGap | None:
  """Return the nearest unfilled FVG in the trade direction."""
  candidates = [
    f
    for f in fvgs
    if f.direction == direction
    and f.index >= after_index
    and f.bottom <= current_price <= f.top
  ]
  if not candidates:
    # Also accept FVGs price is approaching (within zone or just above/below)
    candidates = [
      f for f in fvgs if f.direction == direction and f.index >= after_index
    ]

  if not candidates:
    return None

  return candidates[-1]
