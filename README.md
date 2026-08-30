# SMC-strategy-bot

A small, self-contained **Smart Money Concepts (SMC)** forex strategy
backtesting bot written in Python. It detects market structure (swing points,
Break of Structure and Change of Character), locates **order blocks** and
**fair value gaps**, turns them into trade setups, and backtests the results on
OHLC candle data.

The bot runs **fully offline** — it can generate reproducible synthetic candles,
so no broker API keys or secrets are required to try it out.

## Features

- Fractal **swing point** detection.
- **Market structure** analysis: Break of Structure (BOS) and Change of
  Character (CHoCH).
- **Order block** and **fair value gap** (imbalance) detection.
- An SMC **strategy** that enters on retracements into order blocks with a
  configurable risk-to-reward target.
- An event-driven **backtester** with position sizing, an equity curve and
  summary statistics (win rate, profit factor, return, max drawdown).
- A **CLI** that renders a price/order-block chart and an equity curve, and
  exports trades to CSV.

## Project layout

```
src/smc_bot/
  data.py         # CSV loading + reproducible synthetic candle generation
  indicators.py   # swing points, BOS/CHoCH, order blocks, fair value gaps
  strategy.py     # SMC setups from market structure
  backtester.py   # event-driven backtest engine + statistics
  cli.py          # command-line entry point (chart + report)
tests/            # pytest unit tests
scripts/install.sh  # idempotent environment setup
```

## Getting started

Requires Python 3.10+.

```bash
# Set up the environment (creates .venv and installs dependencies)
bash scripts/install.sh

# Run a backtest on reproducible synthetic data
.venv/bin/smc-bot --candles 1500 --seed 7 --risk-reward 2 --output output
```

This prints a backtest report and writes `output/backtest.png` (price with
order blocks + equity curve) and `output/trades.csv`.

### Backtest your own data

Provide a CSV with `open,high,low,close` columns (an optional
`time`/`timestamp`/`date` column is used as the index):

```bash
.venv/bin/smc-bot --csv data/eurusd_m15.csv --risk-reward 3
```

### Useful options

| Option | Description | Default |
| --- | --- | --- |
| `--csv PATH` | Backtest a CSV instead of synthetic data | synthetic |
| `--candles N` | Number of synthetic candles | 1500 |
| `--seed N` | Random seed for synthetic data | 7 |
| `--swing-lookback N` | Fractal lookback for swing points | 3 |
| `--risk-reward R` | Reward-to-risk multiple for targets | 2.0 |
| `--only-choch` | Trade reversals (CHoCH) only | off |
| `--equity X` | Starting account equity | 10000 |
| `--risk-per-trade F` | Fraction of equity risked per trade | 0.01 |
| `--output DIR` | Output directory for artifacts | `output` |
| `--no-chart` | Skip rendering the chart | off |

## Running the tests

```bash
.venv/bin/python -m pytest
```

## Disclaimer

This project is for **research and educational purposes only**. It is not
financial advice and does not connect to any live trading account. Synthetic
backtest results are not indicative of real-market performance.
