# SMC XAUUSDc Robot

Python Smart Money Concepts (SMC) robot for **XAUUSDc**. It reads **M5, M15, and H1**, takes up to **three positions** (one per timeframe), uses a **1:2 stop-to-target**, and walks the stop (XL) **up** as the trade moves in profit.

This is not financial advice. Gold is volatile; demo-test on MT5 before going live.

## Strategy summary

| Rule | How the robot does it |
| --- | --- |
| Market | XAUUSDc |
| Timeframes | M5, M15, H1. H1 sets bias; all three can enter |
| Concepts | Order Blocks, BOS, MSS, CHoCH, Fair Value Gaps |
| Positions | Max **3**, one per timeframe |
| Risk : Reward | **1 : 2** (TP = 2 × SL distance) |
| Lot size | Any starting balance uses **0.01**. Every extra **$300** adds **0.01** (`$300=0.01`, `$600=0.02`, `$900=0.03`) |
| XL / trailing SL | At **1R** profit, SL moves to breakeven, then trails **up** with price (down on sells). SL never widens |
| News | Trades through news |
| Frequency | Multiple trades per day allowed |

### How a trade is picked

1. **H1 bias** — latest BOS or MSS says bullish or bearish.
2. **CHoCH / MSS** on M5, M15, or H1 in that same direction.
3. **Displacement** leaves an unmitigated **Order Block** and/or **FVG**.
4. **Entry** is a retest of that zone (price back inside the OB or FVG).
5. **SL** sits just beyond the zone. **TP** is 2× that risk. Confluence score must clear the threshold (default 55).
6. While the trade is open, the robot **adjusts XL up** as price moves in favor.

BOS is continuation (break with the trend). CHoCH is the first break against the trend. MSS is a CHoCH that prints with displacement.

## MetaTrader 5 — paste **fredfxV2** into MetaEditor

Python cannot run inside MetaEditor. Use the MQL5 Expert Advisor [`mt5/fredfxV2.mq5`](mt5/fredfxV2.mq5).

1. Open **MetaEditor** (press F4 in MT5).
2. **File → New → Expert Advisor (template)**. Name it **`fredfxV2`**.
3. Delete the generated template and paste the full file `mt5/fredfxV2.mq5`.
4. Press **F7** (Compile). You want **0 errors**.
5. In MT5 open an **XAUUSDc** chart (any timeframe; the EA reads M5, M15, and H1 itself).
6. Drag **fredfxV2** onto the chart. Tick **Allow Algo Trading**.
7. Turn **Algo Trading** ON in the toolbar. Use a **hedging** account so three positions can stay open.

## Python engine (paper / tests)

```bash
python -m pip install -e ".[dev]"
python -m smc_robot summary
python -m smc_robot backtest
python -m pytest
```

Paper scan on synthetic gold candles:

```bash
python -m smc_robot paper
```

Live MT5 (Windows, terminal running, XAUUSDc in Market Watch):

```bash
python -m pip install -e ".[mt5]"
python -m smc_robot live
```

Edit `config.yaml` for symbol, lot step, trail distance, and confluence score.

## Layout

```
src/smc_robot/
  smc/           swings, BOS/CHoCH/MSS, FVG, order blocks
  signals.py     multi-timeframe confluence
  risk.py        $300 lot formula, 1:2 RR, trailing XL
  robot.py       3-position orchestrator
  broker/        paper + MetaTrader 5
  backtest.py    synthetic XAUUSDc path
```
