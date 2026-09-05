# ML trend/pullback scalper

Python brain + MQL5 safety bridge for **Volatility 50 (1s) Index**, **Volatility 75 Index**, and **XAUUSD**.

This package contains **no SMC logic** (no OB, BOS, MSS, CHoCH, FVG, liquidity sweeps).

```
Market data → Python → ML model → trade score → risk manager
          → command.json → MQ5 → MT5
```

See the repository root `README.md` for architecture, risk rules, and live setup.

```bash
python -m ml_scalper.train_model --source synthetic --symbol V75 --bars 8000
python -m ml_scalper --source synthetic --symbol V75 --analyze
python -m ml_scalper --source synthetic --symbol V75 --replay 400
```

Train all three instruments:

```bash
python -m ml_scalper.train_model --source synthetic --all-symbols --bars 8000
```
