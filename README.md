# XAUUSDm SMC Robot

Python Smart Money Concepts (SMC) robot for **XAUUSDm**. It reads **M5, M15, and H1**, holds **1 position** at a time, uses a **1:2 stop-to-target**, and moves the stop (**XL / SL**) to **breakeven** when the trade reaches +1R.

This is not financial advice. Gold is leveraged; you can lose more than you deposit.

## Strategy summary

| Rule | How the robot does it |
| --- | --- |
| Market | XAUUSDm |
| Timeframes | **H1** bias, **M15** structure, **M5** entry |
| Concepts | Order blocks, BOS, MSS, CHoCH, FVG, liquidity sweep |
| Positions | **1** open trade at a time |
| Frequency | Multiple trades per day after the previous one closes |
| News | Trades through news (no pause) |
| Stop : take profit | **1 : 2** |
| Trade management | When price moves +1R, SL is moved to **breakeven** |
| Lots | Any starting balance. Every **$100** adds **0.01** (minimum 0.01) |

### How a trade is picked

1. **H1 bias** — latest BOS, CHoCH, or MSS says bullish or bearish.
2. **M15** must agree with a recent structure event in that same direction.
3. **M5 liquidity sweep** — price hunts stops beyond a swing high/low, then closes back inside.
4. **Displacement** leaves an unmitigated **order block** and/or **FVG**.
5. **Entry** is a fresh tap of that zone. **SL** sits beyond the zone (and the sweep wick). **TP** is 2× that risk.
6. While the trade is open, once price is **+1R** in profit the robot moves **XL to breakeven**. After the trade closes it may take another the same day.

BOS is continuation (break with the trend). CHoCH is the first break against the trend. MSS is a CHoCH that prints with displacement. A liquidity sweep is a wick through a swing that fails to close beyond it.

Print the same summary from the CLI:

```bash
python -m smc_robot summary
```

## Run the Python robot

```bash
python -m pip install -r requirements.txt
python -m pytest
python -m smc_robot --mode demo --balance 1000
```

Paper scan on an M5 CSV (`time,open,high,low,close`):

```bash
python -m smc_robot --mode paper --csv gold_m5.csv --balance 500
```

Live MetaTrader 5 (Windows terminal running, XAUUSDm in Market Watch):

```bash
python -m pip install -e ".[mt5]"
# copy .env.example to .env and fill login / password / server
python -m smc_robot --mode live
```

## Layout

```
smc_robot/
  smc/           swings, BOS/CHoCH/MSS, FVG, order blocks, liquidity sweeps
  risk.py        $100 lot formula, 1:2 RR, breakeven SL
  robot.py       one-position orchestrator
  broker/        paper + MetaTrader 5
  summary.py     printable strategy summary
```
