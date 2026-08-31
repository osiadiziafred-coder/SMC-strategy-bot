# Python ML SMC Robot (XAUUSDm / MT5)

Python is the decision engine. MQL5 is only the execution bridge. The system does **not** claim a 90% win rate. It optimizes for expectancy, controlled risk, and out-of-sample robustness.

Default symbol: **XAUUSDm** (configurable: XAUUSD, GOLD, XAUUSD.a, …).

## Architecture

Two connected programs, not one EA:

```
Python ML/SMC brain → command.json → MQL5 EA → MT5 broker → status.json → Python
```

Python owns: H1/M30/M15, BOS/MSS/CHoCH, OB, FVG, liquidity sweep/zones, ML score, lot size, backtest, training.

MQL5 owns: validate, execute, one-position, breakeven, **optional** trail (`trail_enabled` / `g_trailOn`), heartbeat timeout, status.json. It never invents BUY/SELL.

- Python lives in `.py` files only.
- MQL5 lives in `.mq5` files only.
- Do **not** paste Python into MetaEditor.

## SMC rules (programmed)

Breaks use **close only**. Swings need `n` bars on both sides (`n=2` internal, `n=5` external).

| Concept | Rule |
|---|---|
| **Liquidity sweep** | Wick through a confirmed pool, close back inside. |
| **Equal-liquidity sweep extra** | Clustered highs/lows within `0.15×ATR` get extra score when swept. |
| **Order block** | Last opposite-body candle before BOS/MSS if impulse ≥ `1.2×ATR`. Dead after a closing break. |
| **FVG** | 3-candle gap (`low[i] > high[i-2]`). Min `0.10×ATR`. Valid until fully filled. |
| **BOS** | Continuation: close beyond last **internal** swing with the trend. |
| **CHoCH** | First reversal: close beyond last **internal** swing against the trend. Not a standalone trigger. |
| **MSS** | External reversal: close beyond last **external** swing against the trend. Priority MSS > CHoCH > BOS. |

Print the same definitions: `python -m smc_robot explain`

## Hybrid entry

Trade only when all of these agree:

H1 bias + M30 confirm + liquidity sweep + OB or FVG + M15 BOS/CHoCH/MSS + ML probability ≥ threshold + grade in `{A+, A}` + spread/margin/daily-risk checks.

## Risk

- Default lot size: **every $100 balance = 0.01 lot** (`sizing_mode: balance_step`). Percent-of-equity sizing remains available.
- Default RR **1:2**. SL comes from structure/OB/FVG plus an ATR buffer.
- Max **1** open position.
- Daily loss / trade / consecutive-loss stops.
- Breakeven at **+1R**. Trail from **+1.5R** only when `trail_enabled` is true (`g_trailOn` in the EA). SL never loosens.
- News: `trade_through_news: true` by default. Set it false to honor the calendar window.

Named entry files (do not paste these into MetaEditor):

| File | Role |
|---|---|
| `smc_ml_brain.py` | Live brain (`python smc_ml_brain.py --mode bridge`) |
| `train_model.py` | Historical SMC feature training |
| `features.py` | Feature engineering |
| `smc_detector.py` | BOS/MSS/CHoCH/OB/FVG/liquidity |
| `mt5_connector.py` | MT5 OHLCV/account |
| `risk_manager.py` | Lots + structure SL/TP |
| `command_manager.py` | `command.json` / `status.json` |
| `config.py` | Settings loader |
| `PythonML_SMC_Bridge.mq5` | Execution EA only |

Train from time-ordered history (MT5 if connected, otherwise generated OHLCV — not random labels):

```bash
python train_model.py --out models/smc_scorer.joblib
# also writes models/smc_model.pkl and python_smc_ml_robot/models/smc_model.pkl
# or
python python_smc_ml_robot/main.py train --out models/smc_scorer.joblib
```

Python package layout. The spec folder `python_smc_ml_robot/` is the public brain
(re-exports the `smc_robot` implementation). MQL5 stays an execution bridge only.

```
python_smc_ml_robot/
├── main.py
├── mt5_connector.py
├── market_data.py
├── smc_engine.py
├── liquidity.py
├── order_blocks.py
├── fvg.py
├── market_structure.py
├── feature_engine.py
├── ml_model.py
├── signal_engine.py
├── risk_manager.py
├── command_bridge.py
├── status_reader.py
├── config.py
├── logger.py
├── requirements.txt
├── models/                 # smc_model.pkl after training
├── data/historical_data/   # time-ordered setup labels
└── logs/
```

| Spec name | Location |
|---|---|
| `main.py` | `python_smc_ml_robot/main.py` (also repo `main.py`) |
| `mt5_connector.py` | `python_smc_ml_robot/mt5_connector.py` |
| `market_data.py` | `python_smc_ml_robot/market_data.py` |
| `smc_engine.py` | `python_smc_ml_robot/smc_engine.py` |
| `market_structure.py` | `python_smc_ml_robot/market_structure.py` |
| `liquidity.py` | `python_smc_ml_robot/liquidity.py` |
| `order_blocks.py` | `python_smc_ml_robot/order_blocks.py` |
| `fvg.py` | `python_smc_ml_robot/fvg.py` |
| `feature_engine.py` | `python_smc_ml_robot/feature_engine.py` |
| `ml_model.py` | `python_smc_ml_robot/ml_model.py` |
| `signal_engine.py` | `python_smc_ml_robot/signal_engine.py` |
| `risk_manager.py` | `python_smc_ml_robot/risk_manager.py` |
| `command_bridge.py` | `python_smc_ml_robot/command_bridge.py` |
| `status_reader.py` | `python_smc_ml_robot/status_reader.py` |
| `config.py` | `python_smc_ml_robot/config.py` (`MIN_ML_SCORE = 0.70`) |
| `logger.py` | `python_smc_ml_robot/logger.py` |
| `PythonML_SMC_Bridge.mq5` | repo root (also `pyhonAI_SMC.mq5`) |

## Run

Full install steps: [docs/SETUP.md](docs/SETUP.md).

```bash
pip install -r requirements.txt
python -m smc_robot explain
python -m smc_robot verify
python -m smc_robot --mode paper
python -m smc_robot train --out models/smc_scorer.joblib
python -m smc_robot backtest
python -m smc_robot walk-forward
pytest
```

Windows + running MT5 terminal:

```bash
pip install MetaTrader5
python -m smc_robot --mode dry      # data only
python -m smc_robot --mode live     # Python API orders
python -m smc_robot --mode bridge   # Python writes files, MQL5 EA executes
```

Install and connect the two parts using [docs/SETUP.md](docs/SETUP.md).

## MQL5 bridge

1. Compile `PythonML_SMC_Bridge.mq5` (same file as `pyhonAI_SMC.mq5` / `PythonAI_SMC.mq5`) in MetaEditor — this EA does **not** invent trades.
2. Attach it to XAUUSDm.
3. Python writes `Common/Files/smc_bridge/command.json`.
4. The EA returns `status.json` (ticket, fill, errors, positions, python_fresh).

If the Python heartbeat is older than 45 seconds, the EA rejects new BUY/SELL commands. Existing positions keep local breakeven and trailing protection.

## ML

Gradient Boosting on tabular SMC features. Train **offline only** (`python -m smc_robot train`). Live trades are logged; they do not auto-retrain the model.

Always split **train → validation (threshold) → held-out test**. Walk-forward repeats that window.

Config: `config/default.yaml`.
