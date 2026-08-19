from __future__ import annotations

import pandas as pd


def ohlc(
    closes: list[float],
    *,
    wick: float = 0.3,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
    rows = []
    prev = closes[0]
    for i, close in enumerate(closes):
        open_ = opens[i] if opens is not None else prev
        high = highs[i] if highs is not None else max(open_, close) + wick
        low = lows[i] if lows is not None else min(open_, close) - wick
        rows.append(
            {
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": 10.0,
            }
        )
        prev = close
    return pd.DataFrame(rows)

