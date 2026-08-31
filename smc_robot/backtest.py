"""Historical replay, metrics, and walk-forward validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from smc_robot.config import Settings
from smc_robot.engine import SmcEngine
from smc_robot.models import Candle, Direction
from smc_robot.risk.protection import Quote
from smc_robot.risk.sizing import SymbolSpec
from smc_robot.smc.sessions import classify_session


@dataclass
class TradeResult:
    direction: Direction
    entry: float
    sl: float
    tp: float
    lots: float
    win: bool
    r_multiple: float
    mfe_r: float
    mae_r: float
    session: str | None = None
    grade: str | None = None


@dataclass
class BacktestReport:
    trades: list[TradeResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.win)

    @property
    def losses(self) -> int:
        return self.total - self.wins

    @property
    def win_rate(self) -> float:
        return self.wins / self.total if self.total else 0.0

    @property
    def average_r(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.r_multiple for t in self.trades) / self.total

    @property
    def expectancy(self) -> float:
        return self.average_r

    @property
    def profit_factor(self) -> float:
        gain = sum(t.r_multiple for t in self.trades if t.r_multiple > 0)
        loss = abs(sum(t.r_multiple for t in self.trades if t.r_multiple < 0))
        if loss <= 0:
            return float("inf") if gain > 0 else 0.0
        return gain / loss

    @property
    def max_consecutive_losses(self) -> int:
        return _max_run(self.trades, winning=False)

    @property
    def max_consecutive_wins(self) -> int:
        return _max_run(self.trades, winning=True)

    def max_drawdown_r(self) -> float:
        equity = 0.0
        peak = 0.0
        dd = 0.0
        for trade in self.trades:
            equity += trade.r_multiple
            peak = max(peak, equity)
            dd = min(dd, equity - peak)
        return abs(dd)

    def as_dict(self) -> dict:
        longs = [t for t in self.trades if t.direction == Direction.BUY]
        shorts = [t for t in self.trades if t.direction == Direction.SELL]
        wins = [t.r_multiple for t in self.trades if t.r_multiple > 0]
        losses = [t.r_multiple for t in self.trades if t.r_multiple < 0]
        net_profit_r = sum(t.r_multiple for t in self.trades)
        sessions: dict[str, list[TradeResult]] = {}
        for trade in self.trades:
            key = trade.session or "UNKNOWN"
            sessions.setdefault(key, []).append(trade)
        return {
            "total_trades": self.total,
            "winning_trades": self.wins,
            "losing_trades": self.losses,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "net_profit_r": net_profit_r,
            "net_profit": net_profit_r,
            "average_r": self.average_r,
            "expectancy": self.expectancy,
            "average_win": (sum(wins) / len(wins)) if wins else 0.0,
            "average_loss": (sum(losses) / len(losses)) if losses else 0.0,
            "largest_win": max(wins) if wins else 0.0,
            "largest_loss": min(losses) if losses else 0.0,
            "max_drawdown_r": self.max_drawdown_r(),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "long_trades": len(longs),
            "short_trades": len(shorts),
            "long_win_rate": (sum(1 for t in longs if t.win) / len(longs)) if longs else 0.0,
            "short_win_rate": (sum(1 for t in shorts if t.win) / len(shorts)) if shorts else 0.0,
            "session_performance": {
                name: {
                    "trades": len(rows),
                    "win_rate": (sum(1 for t in rows if t.win) / len(rows)) if rows else 0.0,
                    "average_r": (sum(t.r_multiple for t in rows) / len(rows)) if rows else 0.0,
                }
                for name, rows in sessions.items()
            },
            "disclaimer": "Historical metrics do not guarantee future results or a 90% win rate.",
        }


def _max_run(trades: list[TradeResult], winning: bool) -> int:
    worst = run = 0
    for trade in trades:
        if trade.win is winning:
            run += 1
            worst = max(worst, run)
        else:
            run = 0
    return worst


def _slice_upto(candles: list[Candle], stamp: datetime) -> list[Candle]:
    return [c for c in candles if c.time <= stamp]


def shift_times(candles: list[Candle], delta: timedelta) -> list[Candle]:
    return [c.model_copy(update={"time": c.time + delta}) for c in candles]


def demo_series() -> tuple[list[Candle], list[Candle], list[Candle]]:
    from smc_robot.data.setups import bullish_structure_candles, m15_buy_setup

    h1 = bullish_structure_candles(n=240, minutes=60)
    m30 = shift_times(bullish_structure_candles(n=240, minutes=30), timedelta(days=6))
    m15 = shift_times(m15_buy_setup() + bullish_structure_candles(n=80, minutes=15), timedelta(days=6))
    return h1, m30, m15


def simulate_outcome(
    future: list[Candle],
    direction: Direction,
    entry: float,
    sl: float,
    tp: float,
    point: float = 0.01,
    spread_points: float = 0.0,
    slippage_points: float = 0.0,
    commission_per_lot: float = 0.0,
    lots: float = 0.01,
    tick_value: float = 1.0,
    tick_size: float = 0.01,
) -> tuple[bool, float, float, float, str]:
    fill_offset = (spread_points + slippage_points) * point
    if direction == Direction.BUY:
        fill = entry + fill_offset
    else:
        fill = entry - fill_offset
    risk = abs(fill - sl)
    if risk <= 0:
        return False, 0.0, 0.0, 0.0, "invalid"
    commission_r = 0.0
    value_per_r = lots * (risk / tick_size) * tick_value if tick_size > 0 else 0.0
    if commission_per_lot > 0 and value_per_r > 0:
        commission_r = (commission_per_lot * lots) / value_per_r
    mfe = 0.0
    mae = 0.0
    for candle in future:
        if direction == Direction.BUY:
            mfe = max(mfe, (candle.high - fill) / risk)
            mae = min(mae, (candle.low - fill) / risk)
            if candle.low <= sl:
                return False, -1.0 - commission_r, mfe, abs(mae), "sl"
            if candle.high >= tp:
                return True, (tp - fill) / risk - commission_r, mfe, abs(mae), "tp"
        else:
            mfe = max(mfe, (fill - candle.low) / risk)
            mae = min(mae, (fill - candle.high) / risk)
            if candle.high >= sl:
                return False, -1.0 - commission_r, mfe, abs(mae), "sl"
            if candle.low <= tp:
                return True, (fill - tp) / risk - commission_r, mfe, abs(mae), "tp"
    last = future[-1].close if future else fill
    if direction == Direction.BUY:
        r_mult = (last - fill) / risk - commission_r
    else:
        r_mult = (fill - last) / risk - commission_r
    return r_mult > 0, r_mult, mfe, abs(mae), "timeout"


def run_backtest(
    h1: list[Candle],
    m30: list[Candle],
    m15: list[Candle],
    settings: Settings | None = None,
    spec: SymbolSpec | None = None,
    balance: float = 10_000.0,
    start_index: int = 80,
) -> BacktestReport:
    settings = settings or Settings()
    spec = spec or SymbolSpec(name=settings.symbol)
    engine = SmcEngine(settings)
    report = BacktestReport()
    last_signal = None
    for i in range(start_index, len(m15) - 2):
        closed = m15[: i + 1]
        stamp = closed[-1].time
        h1_w = _slice_upto(h1, stamp)
        m30_w = _slice_upto(m30, stamp)
        if len(h1_w) < 30 or len(m30_w) < 40:
            continue
        last = closed[-1]
        quote = Quote(
            bid=last.close,
            ask=last.close + spec.point * 20,
            time=last.time,
            spread_points=20,
        )
        decision = engine.evaluate(h1_w, m30_w, closed, quote, spec, balance, [20, 20, 21])
        if decision.signal is None:
            continue
        if decision.signal.signal_id == last_signal:
            continue
        last_signal = decision.signal.signal_id
        plan = decision.signal.plan
        costs = settings.backtest
        win, r_mult, mfe, mae, _exit = simulate_outcome(
            m15[i + 1 :],
            plan.direction,
            plan.entry,
            plan.sl,
            plan.tp,
            point=spec.point,
            spread_points=costs.spread_points,
            slippage_points=costs.slippage_points,
            commission_per_lot=costs.commission_per_lot,
            lots=plan.lots,
            tick_value=spec.tick_value,
            tick_size=spec.tick_size,
        )
        report.trades.append(
            TradeResult(
                direction=plan.direction,
                entry=plan.entry,
                sl=plan.sl,
                tp=plan.tp,
                lots=plan.lots,
                win=win,
                r_multiple=r_mult,
                mfe_r=mfe,
                mae_r=mae,
                session=classify_session(closed[-1].time, settings.sessions).value,
                grade=decision.signal.grade.value,
            )
        )
    return report


def walk_forward(
    h1: list[Candle],
    m30: list[Candle],
    m15: list[Candle],
    settings: Settings | None = None,
    folds: int = 3,
) -> list[dict]:
    settings = settings or Settings()
    n = len(m15)
    fold_size = max(40, n // (folds + 2))
    results = []
    for fold in range(folds):
        test_start = (fold + 2) * fold_size
        test_end = min(n, test_start + fold_size)
        if test_end - test_start < 20:
            continue
        report = run_backtest(
            h1,
            m30,
            m15[:test_end],
            settings=settings,
            start_index=max(80, test_start),
        )
        payload = report.as_dict()
        payload["fold"] = fold
        payload["test_start"] = test_start
        payload["test_end"] = test_end
        results.append(payload)
    return results
