# Python ML SMC Robot (XAUUSDm / MT5)

Python is the decision engine. MQL5 is only the execution bridge. The system does **not** claim a 90% win rate. It optimizes for expectancy, controlled risk, and out-of-sample robustness.

Default symbol: **XAUUSDm** (configurable: XAUUSD, GOLD, XAUUSD.a, …).

## Architecture

```
Market data → H1 bias → M30 confirm → M15 sweep/OB/FVG/structure
→ premium/discount + displacement + session/news
→ feature vector → Gradient Boosting probability
→ SMC + ML + risk + spread checks
→ one position → MQL5 execute → BE / structure trail → journal
```

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

- Primary lot size: **percent of equity** from SL distance and tick value.
- Default RR **1:2**. TP can clip before obvious opposing liquidity if 1.2R still remains.
- Max **1** open position.
- Daily loss / trade / consecutive-loss stops.
- Breakeven at **+1R**. Structure trail from **+1.5R**.
- News is configurable (`allow`, `avoid_high`, `window`, `after_only`). Default is `allow`.

## Run

```bash
pip install -r requirements.txt
python -m smc_robot explain
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

## MQL5 bridge

1. Compile `pyhonAI_SMC.mq5` (or `PythonAI_SMC.mq5`) in MetaEditor — this EA does **not** invent trades.
2. Attach it to XAUUSDm.
3. Python writes `Common/Files/smc_bridge/command.json`.
4. The EA returns `status.json` (ticket, fill, errors, positions).

If Python disconnects, the EA does not open new trades. It can still move SL to breakeven on an existing position.

## ML

Gradient Boosting on tabular SMC features. Train **offline only** (`python -m smc_robot train`). Live trades are logged; they do not auto-retrain the model.

Always split **train → validation (threshold) → held-out test**. Walk-forward repeats that window.

Config: `config/default.yaml`.
