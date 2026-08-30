"""A minimal event-driven backtester for SMC trade setups.

The engine walks candles forward, keeps at most one open position at a time and
simulates limit-order entries into order blocks together with fixed
stop-loss / take-profit exits. Position sizing risks a constant fraction of
current equity per trade so results are expressed in comparable R multiples.

Simplifying assumptions (documented so results are interpreted correctly):

* Entries are limit fills at the setup's entry price.
* Exits are evaluated from the candle *after* entry. If a candle spans both the
  stop and the target, the stop is assumed to trigger first (conservative).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .indicators import Direction
from .strategy import StrategyConfig, TradeSetup, build_setups


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 10_000.0
    risk_per_trade: float = 0.01  # fraction of equity risked per trade


@dataclass
class Trade:
    direction: Direction
    entry_index: int
    entry_price: float
    exit_index: int
    exit_price: float
    outcome: str  # "win" | "loss"
    r_multiple: float
    pnl: float
    equity_after: float


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: pd.Series
    stats: dict = field(default_factory=dict)


def _hit_long(candle_low: float, candle_high: float, stop: float, target: float) -> str | None:
    if candle_low <= stop:
        return "loss"
    if candle_high >= target:
        return "win"
    return None


def _hit_short(candle_low: float, candle_high: float, stop: float, target: float) -> str | None:
    if candle_high >= stop:
        return "loss"
    if candle_low <= target:
        return "win"
    return None


def run_backtest(
    df: pd.DataFrame,
    setups: list[TradeSetup] | None = None,
    strategy_config: StrategyConfig | None = None,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run the SMC backtest and return trades, an equity curve and summary stats."""

    config = config or BacktestConfig()
    if setups is None:
        setups = build_setups(df, config=strategy_config)

    setups = sorted(setups, key=lambda s: s.active_from)
    lows = df["low"].to_numpy()
    highs = df["high"].to_numpy()
    n = len(df)

    equity = config.initial_equity
    equity_points: list[float] = []
    trades: list[Trade] = []

    open_trade: dict | None = None
    setup_cursor = 0
    pending: list[TradeSetup] = []

    for i in range(n):
        # Promote newly-active setups into the pending pool.
        while setup_cursor < len(setups) and setups[setup_cursor].active_from <= i:
            pending.append(setups[setup_cursor])
            setup_cursor += 1
        pending = [s for s in pending if s.expires_at >= i]

        if open_trade is not None:
            direction = open_trade["direction"]
            checker = _hit_long if direction == Direction.BULLISH else _hit_short
            outcome = checker(float(lows[i]), float(highs[i]), open_trade["stop"], open_trade["target"])
            if outcome is not None:
                exit_price = open_trade["stop"] if outcome == "loss" else open_trade["target"]
                r = -1.0 if outcome == "loss" else open_trade["rr"]
                pnl = r * open_trade["risk_cash"]
                equity += pnl
                trades.append(
                    Trade(
                        direction=direction,
                        entry_index=open_trade["entry_index"],
                        entry_price=open_trade["entry"],
                        exit_index=i,
                        exit_price=exit_price,
                        outcome=outcome,
                        r_multiple=r,
                        pnl=pnl,
                        equity_after=equity,
                    )
                )
                open_trade = None

        if open_trade is None:
            for setup in list(pending):
                if i <= setup.active_from:
                    continue
                filled = (
                    lows[i] <= setup.entry
                    if setup.direction == Direction.BULLISH
                    else highs[i] >= setup.entry
                )
                if filled:
                    risk_price = setup.risk
                    if risk_price <= 0:
                        pending.remove(setup)
                        continue
                    rr = setup.reward / risk_price
                    open_trade = {
                        "direction": setup.direction,
                        "entry_index": i,
                        "entry": setup.entry,
                        "stop": setup.stop_loss,
                        "target": setup.take_profit,
                        "rr": rr,
                        "risk_cash": equity * config.risk_per_trade,
                    }
                    pending.remove(setup)
                    break

        equity_points.append(equity)

    equity_curve = pd.Series(equity_points, index=df.index, name="equity")
    stats = _compute_stats(trades, equity_curve, config.initial_equity)
    return BacktestResult(trades=trades, equity_curve=equity_curve, stats=stats)


def _compute_stats(trades: list[Trade], equity_curve: pd.Series, initial_equity: float) -> dict:
    wins = [t for t in trades if t.outcome == "win"]
    losses = [t for t in trades if t.outcome == "loss"]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)

    final_equity = float(equity_curve.iloc[-1]) if len(equity_curve) else initial_equity
    running_max = equity_curve.cummax() if len(equity_curve) else equity_curve
    drawdown = (equity_curve - running_max) if len(equity_curve) else equity_curve
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0

    return {
        "num_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(trades)) if trades else 0.0,
        "total_r": sum(t.r_multiple for t in trades),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0,
        "initial_equity": initial_equity,
        "final_equity": final_equity,
        "return_pct": (final_equity / initial_equity - 1.0) * 100.0,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": (max_drawdown / running_max.max() * 100.0) if len(equity_curve) and running_max.max() else 0.0,
    }
