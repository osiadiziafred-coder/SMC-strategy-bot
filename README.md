# SMC-strategy-bot

Two independent trading stacks live in this repository:

1. **ML scalper** (`ml_scalper/`) — a machine-learning trend/pullback scalper for **Volatility 50 (1s) Index**, **Volatility 75 Index**, and **XAUUSD**. Completely separate from Smart Money Concepts.
2. **SMC research** (other branches / packages) — order-block / BOS style tooling, not used by the scalper.

This README covers the ML scalper.

## Architecture

```
Market data → Python → ML model → trade score → risk manager
          → command.json → MQ5 bridge → MT5
```

Python is the brain. MQL5 is the execution and protection layer. Python never sends orders to the broker; the EA never invents BUY/SELL.

## Instruments

Each instrument has its **own config and trained model**:

| Symbol | Model file | Notes |
| --- | --- | --- |
| Volatility 50 (1s) Index | `v50_1s_scalper.joblib` | M15 regime + M5 setup; M1 is precision only, never the sole signal |
| Volatility 75 Index | `v75_scalper.joblib` | Same timeframe roles |
| XAUUSD | `xauusd_scalper.joblib` | Extra spread / session-VWAP execution gates |

## Timeframes

- **M15** — market / trend regime (EMA 20 vs EMA 50)
- **M5** — primary scalping setup (pullback toward EMA/VWAP + momentum)
- **M1** — optional precision entry, not a standalone model input

## ML heads

The model does not predict “the next candle”. It learns:

1. **Direction** — BUY / SELL / NO-TRADE probabilities
2. **Confidence** — those class probabilities
3. **Expected outcome** — P(take-profit is hit before stop-loss) at 1:2 RR

A trade fires only when **technical filters and ML gates both agree**. Confidence thresholds are swept on a chronological holdout (75% is a starting point, not an assumed edge).

## Risk

- 1 open position maximum
- 1:2 minimum reward-to-risk
- ATR / volatility stop
- Move SL to breakeven at +1R
- Multiple trades per day allowed
- Daily-loss halt and consecutive-loss halt
- Skip abnormal spread / volatility
- Automatic lot sizing, per instrument

## Quick start (offline)

```bash
pip install -r requirements.txt

# Train one instrument (or --all-symbols)
python -m ml_scalper.train_model --source synthetic --symbol "Volatility 75 Index" --bars 8000

# Regime readout
python -m ml_scalper --source synthetic --symbol "Volatility 75 Index" --analyze

# Dry-run the full pipeline (writes ml_scalper_bridge/command.json)
python -m ml_scalper --source synthetic --symbol "Volatility 75 Index" --replay 400
```

## Live (Windows + MetaTrader 5)

1. Copy `mql5/ML_Scalper_Bridge.mq5` into `MQL5/Experts`, compile, attach to the chart of the instrument you are trading.
2. The EA reads/writes `Terminal\Common\Files\ml_scalper_bridge\`.
3. Train on real history, then run the brain:

```bash
python -m ml_scalper.train_model --source mt5 --symbol "XAUUSD" --bars 20000
python -m ml_scalper --source mt5 --symbol "XAUUSD" \
    --bridge-dir "C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\ml_scalper_bridge"
```

Environment overrides use the `SCALP_` prefix, e.g. `SCALP_SYMBOL=XAUUSD`.

## Disclaimer

Research and education only. Not financial advice. Synthetic results are not live-market performance. Test on demo before risking capital.
