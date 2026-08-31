# How to run the Python ML + MQL5 system

Python is the brain. The `.mq5` file is only the MetaTrader 5 execution arm. Never paste Python into MetaEditor.

Quick start:

1. `pip install -r requirements.txt`
2. Compile `PythonML_SMC_Bridge.mq5` in MetaEditor (F7, 0 errors) and attach it to XAUUSDm.
3. `python train_model.py --out models/smc_scorer.joblib`
   (also writes `models/smc_model.pkl`)
4. Point `bridge.directory` at `Common\Files\smc_bridge`.
5. `python smc_ml_brain.py --mode bridge`
   or `python python_smc_ml_robot/main.py --mode bridge`

ML gate: `scoring.min_ml_score` / `MIN_ML_SCORE` default **0.70**. Allowed: 0.60, 0.65, 0.70, 0.75, 0.80, 0.85.

Live/bridge mode will not send BUY/SELL unless the trained model file is loaded.

## What you need

- Windows PC with a running **MetaTrader 5** terminal
- A broker account that lists **XAUUSDm** (or set `symbol` in `config/default.yaml`)
- Python 3.10+
- Algo Trading enabled in MT5

Linux CI can run paper tests and the file-bridge protocol. It cannot attach a live MT5 terminal.

## 1. Install Python

```bash
pip install -r requirements.txt
```

Optional live MT5 API (Windows only):

```bash
pip install MetaTrader5
```

Copy `.env.example` if present, or set:

```
MT5_LOGIN=...
MT5_PASSWORD=...
MT5_SERVER=...
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

## 2. Install the MQL5 EA

1. Open MetaEditor.
2. Copy `PythonML_SMC_Bridge.mq5` (or `pyhonAI_SMC.mq5` / `PythonAI_SMC.mq5`) into `MQL5\Experts`.
3. Press **F7**. You must get 0 errors.
4. In MT5: attach the EA to an **XAUUSDm** chart.
5. Allow DLL/file imports if asked. Enable **Algo Trading**.

The EA reads and writes:

`Terminal\Common\Files\smc_bridge\command.json`  
`Terminal\Common\Files\smc_bridge\status.json`

On Windows, point `bridge.directory` in YAML at that Common Files folder, for example:

`C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\smc_bridge`

## 3. Train the model offline

```bash
python train_model.py --out models/smc_scorer.joblib
# or
python -m smc_robot train --out models/smc_scorer.joblib
```

The trainer downloads XAUUSDm H1/M30/M15 from MT5 when the terminal is available. Otherwise it uses a time-ordered gold-like OHLCV series. It extracts real SMC features, labels from **future** candles only, splits train → validation → test **without shuffling**, and saves `models/smc_scorer.joblib`.

It prefers XGBoost, then LightGBM, then sklearn Gradient Boosting / Random Forest. Live trades load this file; they do not refit.

## 4. Start the system

Paper (no MT5):

```bash
python -m smc_robot --mode paper
```

MT5 data, no orders:

```bash
python -m smc_robot --mode dry
```

Python sends orders through the MetaTrader5 package:

```bash
python -m smc_robot --mode live
```

Python writes files; the EA executes (recommended split):

```bash
python -m smc_robot --mode bridge
```

## 5. Verify

```bash
python -m smc_robot verify
python -m smc_robot backtest
python -m smc_robot walk-forward
pytest
```

`verify` checks Python import, MQL5 static validity, file-bridge BUY/SELL, SL/TP, breakeven, structure trail, one-position, daily risk, duplicate block, ML load, backtest, logging, and fail-closed behavior.

## 6. Demo, then live

1. Historical backtest  
2. Walk-forward  
3. Demo account with `--mode bridge`  
4. Small live size only after the journal looks sane  

No 90% win-rate claim. Past metrics do not guarantee future results.
