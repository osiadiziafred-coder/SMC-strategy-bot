# FredFx V1 m5

**FredFx V1 m5** is the XAUUSDM Smart Money Concepts Expert Advisor.
Attach it to an **XAUUSDM M5** chart in MetaTrader 5.

This is not financial advice. Gold is leveraged; you can lose more than you deposit.

## Strategy

| Rule | Behavior |
| --- | --- |
| Name | **FredFx V1 m5** |
| Market | XAUUSDM |
| Chart | M5 entry (also reads M15 and H1) |
| SMC | Order blocks, BOS, MSS, CHoCH, FVG |
| Positions | 1 open trade at a time |
| Frequency | Several trades per day after the previous one closes |
| News | Trades through news |
| Stop : take profit | **1 : 2** |
| Stop | Trails up on buys (down on sells) as price moves |
| Lots | Every **$100** adds **0.01** (minimum 0.01) |

## Compile in MetaTrader 5 (this produces the robot)

MetaEditor is the only compiler that can build the `.ex5` file. This environment cannot emit `.ex5`.

1. Open **MetaTrader 5**.
2. Press **Ctrl+Shift+D** (File → Open Data Folder).
3. Copy `MQL5/Experts/FredFx_V1_m5.mq5` into that folder’s `MQL5/Experts/` directory.
4. Press **F4** to open **MetaEditor**.
5. Open `FredFx_V1_m5.mq5` and press **F7** (Compile).
6. You should see `FredFx_V1_m5.ex5` with **0 errors**.
7. In MT5, open **XAUUSDM, M5**, drag **FredFx V1 m5** onto the chart.
8. Enable **Algo Trading**.

The full Expert Advisor source is:

`MQL5/Experts/FredFx_V1_m5.mq5`

## Python check (same strategy)

```bash
python -m pip install -r requirements.txt
python scripts/compile_fredfx.py
python -m pytest
python -m smc_robot --mode demo --balance 1000
```
