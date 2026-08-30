import pandas as pd

from smc_bot.backtester import BacktestConfig, run_backtest
from smc_bot.data import SyntheticConfig, generate_synthetic
from smc_bot.indicators import Direction, OrderBlock
from smc_bot.strategy import TradeSetup


def _long_setup(entry, stop, target, active_from=0):
    ob = OrderBlock(index=active_from, direction=Direction.BULLISH, top=entry, bottom=stop)
    return TradeSetup(
        direction=Direction.BULLISH,
        active_from=active_from,
        expires_at=active_from + 100,
        entry=entry,
        stop_loss=stop,
        take_profit=target,
        order_block=ob,
    )


def test_winning_long_trade_hits_target():
    # Candle 0 = break, candle 1 retraces to entry, candle 2 runs to target.
    df = pd.DataFrame(
        {
            "open": [1.00, 1.00, 1.01],
            "high": [1.02, 1.01, 1.10],
            "low": [0.99, 0.995, 1.00],
            "close": [1.01, 1.00, 1.09],
        }
    )
    setup = _long_setup(entry=1.00, stop=0.98, target=1.04, active_from=0)
    result = run_backtest(df, setups=[setup], config=BacktestConfig(initial_equity=10_000, risk_per_trade=0.01))

    assert result.stats["num_trades"] == 1
    assert result.trades[0].outcome == "win"
    assert result.trades[0].pnl > 0
    assert result.stats["final_equity"] > 10_000


def test_losing_long_trade_hits_stop():
    df = pd.DataFrame(
        {
            "open": [1.00, 1.00, 1.00],
            "high": [1.02, 1.01, 1.00],
            "low": [0.99, 0.995, 0.97],
            "close": [1.01, 1.00, 0.98],
        }
    )
    setup = _long_setup(entry=1.00, stop=0.98, target=1.04, active_from=0)
    result = run_backtest(df, setups=[setup], config=BacktestConfig(initial_equity=10_000, risk_per_trade=0.01))

    assert result.stats["num_trades"] == 1
    assert result.trades[0].outcome == "loss"
    assert result.trades[0].pnl < 0
    assert result.stats["final_equity"] < 10_000


def test_equity_curve_length_matches_candles():
    df = generate_synthetic(SyntheticConfig(n=600, seed=9))
    result = run_backtest(df)
    assert len(result.equity_curve) == len(df)
    assert set(result.stats) >= {"num_trades", "win_rate", "profit_factor", "return_pct", "max_drawdown"}


def test_end_to_end_synthetic_backtest_runs():
    df = generate_synthetic(SyntheticConfig(n=1500, seed=7))
    result = run_backtest(df)
    # The engine should actually take trades on a realistic-length series.
    assert result.stats["num_trades"] > 0
