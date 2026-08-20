# XAUUSDM SMC Trading Robot

Python Smart Money Concepts robot for **XAUUSDM**. It reads **H1 / M15 / M5**, takes **one position at a time**, sizes lots from account balance, targets **1:2** risk-to-reward, and **trails the stop in the trade’s favor** as price moves. It can open **several trades in a day**, including around news.

This is not financial advice. Gold is leveraged; you can lose more than you deposit.

## Strategy summary

| Topic | How the robot works |
| --- | --- |
| Market | XAUUSDM (Gold) |
| Style | SMC: order blocks, BOS, MSS, CHoCH, FVG |
| Charts | H1 bias, M15 confirmation, M5 entry |
| Positions | 1 open trade at a time |
| Frequency | Many trades per day after the previous one closes |
| News | No news filter — it can trade through news |
| Stop : target | **1 : 2** (risk 1, take profit 2) |
| Stop management | When price moves in profit, SL is adjusted up on buys (down on sells) |
| Lot size | Any starting balance. **Every $100 adds 0.01 lot** (min 0.01) |

### Lot examples

- $50–$100 → 0.01
- $200 → 0.02
- $1,000 → 0.10
- $5,000 → 0.50

### What each SMC piece does

1. **H1 BOS / MSS / CHoCH** — higher-timeframe direction (buy bias or sell bias).
2. **M15 CHoCH / MSS / BOS** — the same direction must already be visible on M15.
3. **M5 order block + FVG** — entry is a tap of an unmitigated bullish/bearish **order block** or **fair value gap**.
4. **Stop** sits beyond that zone. **Take profit** is twice the stop distance.
5. **Trail** — at +1R the stop moves to breakeven, then it follows price so a long stop only ratchets **up**.

The robot only fires when those pieces line up (confluence). It does not place a second trade while one is still open.

## Run it

```bash
python -m pip install -r requirements.txt
python -m pytest
python -m smc_robot --mode demo --balance 1000
```

Paper backtest from your own M5 CSV (`time,open,high,low,close`):

```bash
python -m smc_robot --mode paper --csv gold_m5.csv --balance 1000
```

Live MetaTrader 5 (Windows terminal, symbol `XAUUSDM`):

```bash
pip install MetaTrader5
# copy .env.example to .env and set MT5_LOGIN / MT5_PASSWORD / MT5_SERVER
python -m smc_robot --mode live
```

## Project layout

- `smc_robot/smc/` — BOS, CHoCH, MSS, FVG, order blocks, multi-timeframe strategy
- `smc_robot/risk.py` — 0.01 per $100, 1:2 targets, trailing stop
- `smc_robot/broker/` — paper/backtest engine and optional MT5 adapter
- `smc_robot/robot.py` — one-position loop, daily trade reopen, SL trail
