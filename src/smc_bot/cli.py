"""Command-line interface for the SMC strategy bot.

Examples
--------
Run a backtest on reproducible synthetic data and write a chart::

    smc-bot --candles 1500 --seed 7 --output output

Backtest a CSV of your own OHLC candles::

    smc-bot --csv data/eurusd_m15.csv --risk-reward 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .backtester import BacktestConfig, run_backtest
from .data import SyntheticConfig, generate_synthetic, load_csv
from .strategy import StrategyConfig, build_setups


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smc-bot",
        description="Backtest a Smart Money Concepts forex strategy.",
    )
    parser.add_argument("--version", action="version", version=f"smc-bot {__version__}")

    source = parser.add_argument_group("data source")
    source.add_argument("--csv", type=Path, help="Path to an OHLC CSV file (defaults to synthetic data).")
    source.add_argument("--candles", type=int, default=1500, help="Number of synthetic candles to generate.")
    source.add_argument("--seed", type=int, default=7, help="Random seed for synthetic data.")

    strat = parser.add_argument_group("strategy")
    strat.add_argument("--swing-lookback", type=int, default=3, help="Fractal lookback for swing points.")
    strat.add_argument("--risk-reward", type=float, default=2.0, help="Reward-to-risk multiple for targets.")
    strat.add_argument("--only-choch", action="store_true", help="Trade reversals (CHoCH) only.")

    risk = parser.add_argument_group("risk / account")
    risk.add_argument("--equity", type=float, default=10_000.0, help="Starting account equity.")
    risk.add_argument("--risk-per-trade", type=float, default=0.01, help="Fraction of equity risked per trade.")

    out = parser.add_argument_group("output")
    out.add_argument("--output", type=Path, default=Path("output"), help="Directory for chart/trade artifacts.")
    out.add_argument("--no-chart", action="store_true", help="Skip rendering the chart PNG.")

    return parser


def _load_data(args: argparse.Namespace):
    if args.csv is not None:
        print(f"Loading candles from {args.csv}")
        return load_csv(args.csv)
    print(f"Generating {args.candles} synthetic candles (seed={args.seed})")
    return generate_synthetic(SyntheticConfig(n=args.candles, seed=args.seed))


def _print_report(setups, result) -> None:
    stats = result.stats
    print("\n" + "=" * 48)
    print("SMC STRATEGY BACKTEST REPORT")
    print("=" * 48)
    print(f"Setups detected : {len(setups)}")
    print(f"Trades taken    : {stats['num_trades']}")
    print(f"Wins / Losses   : {stats['wins']} / {stats['losses']}")
    print(f"Win rate        : {stats['win_rate'] * 100:.1f}%")
    print(f"Total R         : {stats['total_r']:+.2f}R")
    print(f"Profit factor   : {stats['profit_factor']:.2f}")
    print(f"Start equity    : {stats['initial_equity']:,.2f}")
    print(f"Final equity    : {stats['final_equity']:,.2f}")
    print(f"Net return      : {stats['return_pct']:+.2f}%")
    print(f"Max drawdown    : {stats['max_drawdown']:,.2f} ({stats['max_drawdown_pct']:.2f}%)")
    print("=" * 48)


def _render_chart(df, setups, result, output_dir: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax_price, ax_equity) = plt.subplots(
        2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [2, 1]}, sharex=False
    )

    ax_price.plot(range(len(df)), df["close"].to_numpy(), color="#1f77b4", linewidth=0.9, label="Close")
    for setup in setups:
        color = "#2ca02c" if setup.direction.value == "bullish" else "#d62728"
        ax_price.axhspan(
            setup.order_block.bottom,
            setup.order_block.top,
            xmin=max(0, setup.active_from / len(df) - 0.01),
            xmax=min(1, setup.active_from / len(df) + 0.02),
            color=color,
            alpha=0.25,
        )
    for trade in result.trades:
        marker = "^" if trade.direction.value == "bullish" else "v"
        entry_color = "#2ca02c" if trade.outcome == "win" else "#d62728"
        ax_price.scatter(trade.entry_index, trade.entry_price, marker=marker, color=entry_color, s=45, zorder=5)
    ax_price.set_title("Price with SMC order blocks and trade entries")
    ax_price.set_ylabel("Price")
    ax_price.legend(loc="upper left")
    ax_price.grid(alpha=0.2)

    ax_equity.plot(range(len(result.equity_curve)), result.equity_curve.to_numpy(), color="#8c564b")
    ax_equity.set_title("Equity curve")
    ax_equity.set_xlabel("Candle #")
    ax_equity.set_ylabel("Equity")
    ax_equity.grid(alpha=0.2)

    output_dir.mkdir(parents=True, exist_ok=True)
    chart_path = output_dir / "backtest.png"
    fig.tight_layout()
    fig.savefig(chart_path, dpi=110)
    plt.close(fig)
    return chart_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    df = _load_data(args)
    strategy_config = StrategyConfig(
        swing_lookback=args.swing_lookback,
        risk_reward=args.risk_reward,
        only_choch=args.only_choch,
    )
    setups = build_setups(df, config=strategy_config)
    result = run_backtest(
        df,
        setups=setups,
        config=BacktestConfig(initial_equity=args.equity, risk_per_trade=args.risk_per_trade),
    )

    _print_report(setups, result)

    if not args.no_chart:
        chart_path = _render_chart(df, setups, result, args.output)
        print(f"\nChart written to {chart_path}")

        trades_path = args.output / "trades.csv"
        import pandas as pd

        pd.DataFrame([t.__dict__ for t in result.trades]).to_csv(trades_path, index=False)
        print(f"Trades written to {trades_path}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
