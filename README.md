# FredFx V1 m5

**FredFx V1 m5** is the XAUUSDm Smart Money Concepts Expert Advisor.
Attach it to an **XAUUSDm M5** chart in MetaTrader 5.

This is not financial advice. Gold is leveraged; you can lose more than you deposit.

## Strategy summary

| Rule | Behavior |
| --- | --- |
| Name | **FredFx V1 m5** |
| Market | XAUUSDm |
| Chart | M5 entry (also reads M15 and H1) |
| SMC | Order blocks, BOS, MSS, CHoCH, FVG, liquidity sweep |
| Positions | 1 open trade at a time |
| Frequency | Several trades per day after the previous one closes |
| News | Trades through news |
| Stop : take profit | **1 : 2** |
| Stop | At +1R, SL (XL) moves to **breakeven** |
| Lots | Every **$100** adds **0.01** (minimum 0.01) |

### How a trade is picked

1. **H1 bias** — latest BOS, CHoCH, or MSS.
2. **M15** must agree.
3. **M5 liquidity sweep** — wick through a swing, close back inside.
4. Entry is a fresh tap of an unmitigated **order block** or **FVG**.
5. **SL** sits beyond the zone and the sweep wick. **TP** is 2× that risk.
6. When price moves +1R, SL is moved to breakeven.

## Full code (compile this in MetaTrader 5)

The complete robot is one file:

**`MQL5/Experts/FredFx_V1_m5.mq5`**

MetaEditor is the only compiler that can build the `.ex5` file.

1. Open **MetaTrader 5**.
2. Press **Ctrl+Shift+D** (File → Open Data Folder).
3. Copy `MQL5/Experts/FredFx_V1_m5.mq5` into that folder’s `MQL5/Experts/` directory.
4. Press **F4** to open **MetaEditor**.
5. Open `FredFx_V1_m5.mq5` and press **F7** (Compile).
6. You should see `FredFx_V1_m5.ex5` with **0 errors**.
7. In MT5, open **XAUUSDm, M5**, drag **FredFx V1 m5** onto the chart.
8. Enable **Algo Trading**.

## Python check (same strategy)

```bash
python -m pip install -r requirements.txt
python scripts/compile_fredfx.py
python -m pytest
python -m smc_robot summary
python -m smc_robot --mode demo --balance 1000
```
