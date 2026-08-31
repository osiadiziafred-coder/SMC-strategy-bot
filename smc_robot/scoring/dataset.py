"""Build labeled SMC feature rows from closed candles only.

Features at bar i use candles with time <= bar i.
Labels use only later bars. Time order is preserved.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from smc_robot.backtest import simulate_outcome
from smc_robot.config import Settings
from smc_robot.models import Candle, Direction
from smc_robot.risk.protection import Quote
from smc_robot.risk.sizing import SymbolSpec
from smc_robot.risk.trade_plan import build_trade_plan
from smc_robot.scoring import extract_features, feature_vector, find_setup_parts
from smc_robot.smc.analyze import analyze_timeframe
from smc_robot.smc.conditions import analyze_conditions


def _slice_upto(candles: list[Candle], stamp: datetime) -> list[Candle]:
    return [c for c in candles if c.time <= stamp]


def build_labeled_dataset(
    h1: list[Candle],
    m30: list[Candle],
    m15: list[Candle],
    settings: Settings | None = None,
    spec: SymbolSpec | None = None,
    balance: float = 10_000.0,
    start_index: int = 80,
    step: int = 2,
    horizon: int = 16,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    settings = settings or Settings()
    spec = spec or SymbolSpec(name=settings.symbol)
    features: list[np.ndarray] = []
    labels: list[int] = []
    meta: list[dict] = []
    for i in range(start_index, len(m15) - 3, max(1, step)):
        closed = m15[max(0, i - 499) : i + 1]
        stamp = closed[-1].time
        h1_w = _slice_upto(h1, stamp)[-300:]
        m30_w = _slice_upto(m30, stamp)[-400:]
        if len(h1_w) < 30 or len(m30_w) < 40 or len(closed) < 40:
            continue
        h1_a = analyze_timeframe(h1_w, settings)
        m30_a = analyze_timeframe(m30_w, settings)
        m15_a = analyze_timeframe(closed, settings)
        last = closed[-1]
        spread = last.spread or 20.0
        quote = Quote(
            bid=last.close,
            ask=last.close + spec.point * max(1.0, spread),
            time=last.time,
            spread_points=spread,
        )
        conditions = analyze_conditions(closed, settings, quote.spread_points, [spread])
        future = m15[i + 1 : i + 1 + horizon]
        for direction in (Direction.BUY, Direction.SELL):
            sweep, order_block, fvg, _ = find_setup_parts(direction, m30_a, m15_a, settings)
            feat = extract_features(
                direction, h1_a, m30_a, m15_a, conditions, settings, sweep, order_block, fvg
            )
            label = 0
            row = {
                "index": i,
                "time": stamp.isoformat(),
                "direction": direction.value,
                "label": 0,
                "entry": None,
                "sl": None,
                "tp": None,
                "mfe": None,
                "mae": None,
                "tp_hit": False,
                "sl_hit": False,
                "outcome": "skip",
            }
            if sweep is not None and (order_block is not None or fvg is not None):
                entry = quote.ask if direction == Direction.BUY else quote.bid
                plan = build_trade_plan(
                    direction,
                    entry,
                    sweep,
                    order_block,
                    fvg,
                    conditions.atr,
                    balance,
                    spec,
                    settings,
                )
                if plan is not None and future:
                    win, _r, mfe, mae, exit_reason = simulate_outcome(
                        future,
                        plan.direction,
                        plan.entry,
                        plan.sl,
                        plan.tp,
                        point=spec.point,
                    )
                    label = 1 if win else 0
                    row.update(
                        {
                            "label": label,
                            "entry": plan.entry,
                            "sl": plan.sl,
                            "tp": plan.tp,
                            "mfe": float(mfe),
                            "mae": float(mae),
                            "tp_hit": exit_reason == "tp",
                            "sl_hit": exit_reason == "sl",
                            "outcome": exit_reason,
                        }
                    )
            features.append(feature_vector(feat))
            labels.append(label)
            meta.append(row)
    if not features:
        return np.empty((0, 0)), np.empty((0,), dtype=int), []
    return np.vstack(features), np.asarray(labels, dtype=int), meta
