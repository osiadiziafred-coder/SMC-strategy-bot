"""Swing high / low detection utilities."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SwingPoint:
  index: int
  price: float
  kind: str  # "high" or "low"
  time: pd.Timestamp


def find_swing_highs(df: pd.DataFrame, lookback: int = 5) -> list[SwingPoint]:
  """Return swing highs where high is the max within lookback bars on each side."""
  highs = df["high"].values
  times = df.index
  swings: list[SwingPoint] = []

  for i in range(lookback, len(df) - lookback):
    window = highs[i - lookback : i + lookback + 1]
    if highs[i] == window.max() and np.sum(window == highs[i]) == 1:
      swings.append(SwingPoint(index=i, price=highs[i], kind="high", time=times[i]))

  return swings


def find_swing_lows(df: pd.DataFrame, lookback: int = 5) -> list[SwingPoint]:
  """Return swing lows where low is the min within lookback bars on each side."""
  lows = df["low"].values
  times = df.index
  swings: list[SwingPoint] = []

  for i in range(lookback, len(df) - lookback):
    window = lows[i - lookback : i + lookback + 1]
    if lows[i] == window.min() and np.sum(window == lows[i]) == 1:
      swings.append(SwingPoint(index=i, price=lows[i], kind="low", time=times[i]))

  return swings


def recent_swing(swings: list[SwingPoint], before_index: int, count: int = 1) -> list[SwingPoint]:
  """Return the most recent `count` swing points before `before_index`."""
  filtered = [s for s in swings if s.index < before_index]
  return filtered[-count:] if filtered else []
