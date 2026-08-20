from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def ensure_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in ("open", "high", "low", "close") if col not in df.columns]
    if missing:
        raise ValueError(f"OHLC frame missing columns: {missing}")
    out = df.copy()
    if "time" not in out.columns:
        out = out.reset_index()
        if "index" in out.columns and "time" not in out.columns:
            out = out.rename(columns={"index": "time"})
    return out.reset_index(drop=True)


def resample_ohlc(df: pd.DataFrame, factor: int) -> pd.DataFrame:
    """Resample a lower-timeframe OHLC series by grouping `factor` bars."""
    if factor <= 1:
        return ensure_ohlc(df)
    src = ensure_ohlc(df)
    rows = []
    usable = len(src) - (len(src) % factor)
    for start in range(0, usable, factor):
        chunk = src.iloc[start : start + factor]
        rows.append(
            {
                "time": chunk["time"].iloc[0],
                "open": float(chunk["open"].iloc[0]),
                "high": float(chunk["high"].max()),
                "low": float(chunk["low"].min()),
                "close": float(chunk["close"].iloc[-1]),
                "volume": float(chunk["volume"].sum()) if "volume" in chunk.columns else 0.0,
            }
        )
    return pd.DataFrame(rows)


TF_MINUTES = {"M5": 5, "M15": 15, "H1": 60}


def factor_from_m5(timeframe: str) -> int:
    minutes = TF_MINUTES[timeframe]
    if minutes % 5 != 0:
        raise ValueError(f"Cannot build {timeframe} from M5")
    return minutes // 5


@dataclass(frozen=True)
class MultiTimeframeBars:
    m5: pd.DataFrame
    m15: pd.DataFrame
    h1: pd.DataFrame

    @classmethod
    def from_m5(cls, m5: pd.DataFrame) -> "MultiTimeframeBars":
        src = ensure_ohlc(m5)
        return cls(
            m5=src,
            m15=resample_ohlc(src, 3),
            h1=resample_ohlc(src, 12),
        )
