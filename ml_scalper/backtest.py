"""Out-of-sample backtest of the technical+ML selection rules on M5 bars.

Used to report win rate / expectancy after training. This is a research tool,
not a live execution path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Config
from .features import live_setup_flags, triple_barrier_labels
from . import indicators as ind
from .ml_model import ScalperModels
from .features import add_direction_features, build_base_matrix


@dataclass
class BacktestResult:
    trades: int
    wins: int
    win_rate: float
    expectancy_R: float
    buy_trades: int
    sell_trades: int

    def as_dict(self) -> dict:
        return {
            "trades": self.trades,
            "wins": self.wins,
            "win_rate": self.win_rate,
            "expectancy_R": self.expectancy_R,
            "buy_trades": self.buy_trades,
            "sell_trades": self.sell_trades,
        }


def run_backtest(
    m15: pd.DataFrame,
    m5: pd.DataFrame,
    m1: pd.DataFrame | None,
    cfg: Config,
    models: ScalperModels,
    start: int | None = None,
) -> BacktestResult:
    base = build_base_matrix(m15, m5, m1, cfg)
    atr_s = ind.atr(m5, cfg.atr_period)
    y_buy = triple_barrier_labels(m5, atr_s, 1, cfg.label_horizon, cfg.atr_sl_mult, cfg.risk_reward)
    y_sell = triple_barrier_labels(m5, atr_s, -1, cfg.label_horizon, cfg.atr_sl_mult, cfg.risk_reward)

    n = len(base)
    i0 = start if start is not None else n // 5  # skip warmup + leave later bars as OOS-ish
    wins = 0
    trades = 0
    buy_n = sell_n = 0
    in_trade_until = -1

    for i in range(i0, n):
        if i <= in_trade_until:
            continue
        if not np.isfinite(y_buy.iloc[i]) or not np.isfinite(y_sell.iloc[i]):
            continue
        row_df = base.iloc[[i]]
        flags = live_setup_flags(row_df.iloc[0], cfg)
        buy_f = add_direction_features(row_df, 1)
        sell_f = add_direction_features(row_df, -1)
        score = models.predict(row_df, buy_f, sell_f)
        buy_ok = flags["buy_setup"] and score.p_buy >= cfg.ml_min_confidence and score.p_tp_buy >= cfg.min_outcome_prob
        sell_ok = flags["sell_setup"] and score.p_sell >= cfg.ml_min_confidence and score.p_tp_sell >= cfg.min_outcome_prob
        side = None
        if buy_ok and (not sell_ok or score.p_buy >= score.p_sell):
            side = "BUY"
        elif sell_ok:
            side = "SELL"
        if side is None:
            continue
        trades += 1
        won = int(y_buy.iloc[i] if side == "BUY" else y_sell.iloc[i])
        wins += won
        if side == "BUY":
            buy_n += 1
        else:
            sell_n += 1
        in_trade_until = i + cfg.label_horizon  # one position max

    wr = wins / trades if trades else 0.0
    exp_r = (wr * cfg.risk_reward - (1.0 - wr)) if trades else 0.0
    return BacktestResult(
        trades=trades,
        wins=wins,
        win_rate=wr,
        expectancy_R=exp_r,
        buy_trades=buy_n,
        sell_trades=sell_n,
    )
