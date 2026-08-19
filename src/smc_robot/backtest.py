"""Synthetic XAUUSDm candles + bar-by-bar paper backtest."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from smc_robot.broker.paper import PaperBroker
from smc_robot.config import RobotConfig
from smc_robot.robot import SMCRobot


def make_gold_trend(
    n: int = 240,
    start: float = 2400.0,
    seed: int = 7,
    drift: float = 0.35,
) -> pd.DataFrame:
    """Build a gold-like OHLC series with swings, displacement, and FVGs."""
    rng = np.random.default_rng(seed)
    rows = []
    price = start
    t = pd.Timestamp("2024-01-02 00:00:00", tz="UTC")
    for i in range(n):
        # Slow uptrend with a mid-series pullback so CHoCH / FVG can form.
        wave = np.sin(i / 9.0) * 1.8
        shock = 0.0
        if i in {40, 80, 140, 190}:
            shock = 4.5 if drift > 0 else -4.5
        if 95 <= i <= 110:
            shock -= 1.2
        # Pull back into the imbalance after displacement so FVG/OB can be tapped.
        if i in range(44, 52) or i in range(84, 92) or i in range(144, 152):
            shock -= 1.6 if drift > 0 else -1.6
        move = drift + wave * 0.15 + shock + float(rng.normal(0, 0.35))
        open_ = price
        close = price + move
        wick = abs(float(rng.normal(0.4, 0.15)))
        high = max(open_, close) + wick
        low = min(open_, close) - wick
        # Force a 3-candle bullish FVG around selected bars.
        if i in {41, 81, 141}:
            low = max(low, rows[-2]["high"] + 0.35) if len(rows) >= 2 else low
        rows.append(
            {
                "time": t + pd.Timedelta(minutes=5 * i),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": 100 + int(rng.integers(0, 40)),
            }
        )
        price = close
    return pd.DataFrame(rows)


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = (
        df.set_index("time")
        .resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
        .reset_index()
    )
    return out


def multi_tf_frames(m5: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "M5": m5.copy(),
        "M15": resample_ohlc(m5, "15min"),
        "H1": resample_ohlc(m5, "1h"),
    }


def make_ob_retest() -> pd.DataFrame:
    """Dip, bounce, bullish BOS / FVG, then a retrace that taps the zone.

    Sized so the default ``swing_length=5`` fractal settings still fire.
    """
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    price = 2400.0
    for i in range(60):
        if i < 8:
            price -= 2.0
            open_, close = price + 1.5, price
            high, low = open_ + 0.3, close - 0.8
        elif i < 20:
            price += 2.2
            open_, close = price - 1.5, price
            high, low = close + 0.8, open_ - 0.3
        elif i < 26:
            price -= 1.0
            open_, close = price + 1.2, price
            high, low = open_ + 0.2, close - 0.5
        elif i < 40:
            price += 3.5
            open_, close = price - 2.5, price
            high, low = close + 0.6, open_ - 0.2
        else:
            price -= 1.6
            open_, close = price + 1.2, price
            high, low = open_ + 0.2, close - 0.4
        opens.append(round(open_, 2))
        highs.append(round(high, 2))
        lows.append(round(low, 2))
        closes.append(round(close, 2))

    rows = []
    start = pd.Timestamp("2024-01-02 00:00:00", tz="UTC")
    for i in range(len(closes)):
        rows.append(
            {
                "time": start + pd.Timedelta(minutes=5 * i),
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": 12.0,
            }
        )
    return pd.DataFrame(rows)


@dataclass
class BacktestResult:
    starting_balance: float
    ending_balance: float
    trades: int
    wins: int
    losses: int
    open_positions: int
    profit: float

    @property
    def win_rate(self) -> float:
        if self.trades == 0:
            return 0.0
        return self.wins / self.trades


def run_backtest(
    config: RobotConfig | None = None,
    bars: int = 400,
    seed: int = 7,
) -> BacktestResult:
    cfg = config or RobotConfig()
    m5 = make_gold_trend(n=bars, seed=seed)
    broker = PaperBroker(cfg)
    robot = SMCRobot(broker, cfg)

    # Walk forward, feeding expanding windows so structure is causal.
    min_bars = 80
    for end in range(min_bars, len(m5)):
        window = m5.iloc[: end + 1].copy()
        frames = multi_tf_frames(window)
        broker.set_frames(frames)
        broker.set_price(float(window.iloc[-1]["close"]), window.iloc[-1]["time"].to_pydatetime())
        robot.step(frames)

    closed = [p for p in broker.account().positions if p.closed]
    wins = sum(1 for p in closed if p.profit > 0)
    losses = sum(1 for p in closed if p.profit <= 0)
    account = broker.account()
    return BacktestResult(
        starting_balance=cfg.starting_balance,
        ending_balance=account.balance,
        trades=len(closed),
        wins=wins,
        losses=losses,
        open_positions=len(account.open_positions),
        profit=account.balance - cfg.starting_balance,
    )
