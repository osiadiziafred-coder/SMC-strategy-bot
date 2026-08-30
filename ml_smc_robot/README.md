# ML + SMC Trading Robot — XAUUSDm (Gold)

A two-part algorithmic trading system:

1. **Python ML/SMC brain** — pulls multi-timeframe data from MetaTrader 5,
   detects Smart Money Concepts (SMC) structure, engineers features, runs a
   **real trained machine-learning model** to score BUY/SELL setups, applies
   risk rules and writes a trade command.
2. **MQL5 safety bridge EA** (`../mql5/SMC_Safety_Bridge.mq5`) — the only
   component that touches the broker. It executes commands from Python and
   independently manages one-position protection, breakeven and trailing stops.

The Python side never places orders directly, and the EA never invents BUY/SELL
signals on its own.

```
MT5 data → SMC detection → feature engineering → trained ML model
        → BUY/SELL probability → SMC validation → risk management
        → command.json → MQL5 bridge → MT5 trade
```

## Architecture / deliverables

| File | Responsibility |
| --- | --- |
| `config.py` | All tunables (symbol, timeframes, `ML_MIN_CONFIDENCE`, risk, paths). |
| `mt5_connector.py` | MT5 live data/execution + offline synthetic/CSV providers. |
| `smc_detector.py` | BOS, MSS, CHoCH, order blocks, FVGs, liquidity sweeps, equal highs/lows, liquidity zones, premium/discount, swings, trend/bias, displacement, volatility. |
| `features.py` | Multi-timeframe, causal, NaN-safe feature matrix + triple-barrier labels. |
| `ml_model.py` | LightGBM/XGBoost/RandomForest wrapper (save/load, importances, per-trade explanation). |
| `train_model.py` | Historical training pipeline with time-ordered validation. |
| `risk_manager.py` | Lot sizing, structural SL/TP at 1:2, breakeven/trailing params, validation. |
| `command_manager.py` | `command.json`/`status.json` bridge, unique IDs, heartbeat, de-duplication. |
| `smc_ml_brain.py` | Orchestrator: data → SMC → features → ML → decision → command. |
| `../mql5/SMC_Safety_Bridge.mq5` | MQL5 safety bridge EA (execution + protection). |

## Installation

Python 3.10+.

```bash
pip install -r ml_smc_robot/requirements.txt
```

On **Windows with a running MetaTrader 5 terminal**, `pip` also installs the
`MetaTrader5` package. On Linux/macOS that package is skipped automatically and
the robot uses the offline synthetic/CSV providers for training and dry-runs.

## Quick start (offline, no terminal required)

```bash
# 1) Train the model on offline synthetic gold data (time-ordered split)
python -m ml_smc_robot.train_model --source synthetic --bars 15000

# 2) Dry-run the full brain pipeline over an offline feed (writes command.json)
python -m ml_smc_robot.smc_ml_brain --source synthetic --replay 2500

# 3) Optional: render a decision chart
python scripts/plot_robot_demo.py --out robot_demo.png
```

## Live usage (Windows + MetaTrader 5)

1. Copy `mql5/SMC_Safety_Bridge.mq5` into `MQL5/Experts`, compile it in
   MetaEditor, and attach it to an **XAUUSDm** chart. The EA reads/writes:
   `Common\Files\smc_bridge\command.json` and `status.json` (it opens files with
   `FILE_COMMON`).
2. Point the brain at the same folder and train against real history, then run:

```bash
# Train on real MT5 history
python -m ml_smc_robot.train_model --source mt5 --bars 30000

# Run the live brain (set the bridge dir to the MT5 Common\Files\smc_bridge path)
python -m ml_smc_robot.smc_ml_brain --source mt5 \
    --bridge-dir "C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\smc_bridge"
```

Configuration can also be overridden via environment variables prefixed with
`SMC_`, e.g. `SMC_ML_MIN_CONFIDENCE=0.75`.

## Decision logic

- **H1** sets directional bias; **M30** must confirm; **M15** provides the entry.
- M15 structure (BOS/MSS/CHoCH or standing trend) must support the direction.
- A valid entry area (order block / FVG) must be present.
- The ML probability for the direction must be ≥ `ML_MIN_CONFIDENCE` (default 0.70).
- Risk is fixed at **1:2**; stops are anchored to structure with an ATR floor.
- Lot size follows `balance / 100 * 0.01`, normalised to the broker's step.
- Otherwise the decision is `NONE` — **the ML model can reject a trade.**

## Safety

- **One position at a time** (enforced by both Python and the EA).
- Every command has a **unique id**; the EA never executes the same id twice.
- Python sends a **heartbeat**; the EA refuses new entries when Python is stale
  but keeps managing breakeven/trailing on any open trade.
- Pre-trade checks: existing position, symbol, spread, lots, SL, TP, ~1:2 RR,
  ML confidence, SMC validity.
- The EA repeats broker-side validation before execution.

## Disclaimer

For research and educational purposes only. Not financial advice. Synthetic
backtests are **not** indicative of real-market performance. Test on a demo
account before risking capital.
