# How to run the Python ML + MQL5 system

Python is the brain. The `.mq5` file is only the MetaTrader 5 execution arm. Never paste Python into MetaEditor.

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
2. Create / replace `MQL5\Experts\pyhonAI_SMC.mq5` with the repo file of the same name.
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
python -m smc_robot train --out models/smc_scorer.joblib
```

The trainer compares Gradient Boosting, Random Forest, and Logistic Regression on a **validation** split, then reports held-out test accuracy. Live trades do not auto-retrain.

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
