# FredFx v1 SMC

**FredFx v1 SMC** is a Python Smart Money Concepts robot for **XAUUSDm**.
It reads **H1 → M15 → M5**, opens **one position at a time**, uses a **1:2** stop-to-target, and moves the stop to **breakeven** once the trade is far enough in profit.

This is not financial advice. Gold is leveraged; you can lose more than you deposit. Demo-test on MetaTrader 5 before going live.

## Strategy summary

| Rule | How the robot does it |
| --- | --- |
| Name | **FredFx v1 SMC** |
| Market | XAUUSDm |
| Timeframes | H1 bias → M15 confirmation → M5 entry |
| Concepts | Order Blocks, BOS, MSS, CHoCH, FVG, liquidity sweeps, liquidity zones |
| Positions | Max **1** |
| Frequency | Multiple trades per day after the previous one closes |
| Risk : Reward | **1 : 2** (TP = 2 × SL distance) |
| Lot size | **0.01** lot for every **$100** (`$100=0.01`, `$200=0.02`, `$500=0.05`, `$1,000=0.10`) |
| Stop | Behind the SMC structure (sweep wick and OB/FVG) |
| Breakeven | At **+1R**, SL moves to entry |
| News | Configurable. Default: keep trading through news |

### How a trade is picked

The robot does **not** enter because one concept prints. Every gate must line up:

1. **H1** — latest BOS, CHoCH, or MSS sets bullish or bearish market structure.
2. **M15** — structure agrees with H1, a liquidity zone is present, and an unmitigated order block or FVG exists in that direction.
3. **M5** — liquidity sweep, then MSS / CHoCH / BOS in the same direction, then a fresh tap of an unmitigated OB or FVG.
4. **Entry** — open exactly one position.
5. **SL** — behind the relevant structure. **TP** is 2× that risk.
6. When price reaches +1R, SL moves to breakeven.
7. After TP or SL, the robot looks for the next valid setup.

```
H1: Determine bullish/bearish market structure
↓
M15: Identify liquidity + OB/FVG + structure confirmation
↓
M5: Wait for liquidity sweep → MSS/CHoCH/BOS → entry confirmation
↓
Entry: Open 1 position
↓
SL: Behind the relevant structure
↓
TP: 1:2 RR
↓
Trade moves into profit: Move SL to breakeven
↓
TP or SL hit: Position closes
↓
No open position: Robot searches for the next valid setup
```

## Install

```bash
python -m pip install -e ".[dev]"
python -m smc_robot summary
python -m pytest
python -m smc_robot --mode demo --balance 1000
```

Paper scan on a CSV of M5 candles (`time,open,high,low,close`):

```bash
python -m smc_robot --mode paper --csv gold_m5.csv --balance 1000
```

See why the latest bar was accepted or rejected:

```bash
python -m smc_robot diagnose --mode demo
```

## Live MetaTrader 5

Python talks to your broker through the MetaTrader 5 terminal (Windows).

1. Install MT5 and log in. Put **XAUUSDm** in Market Watch.
2. Copy `.env.example` to `.env` and fill login, password, server, and terminal path.
3. Install the MT5 extra and start the robot:

```bash
python -m pip install -e ".[mt5]"
python -m smc_robot --mode live
```

Algo Trading must be enabled in MT5. The robot will not open a second position while one is already live.

## News

XAUUSDm can become extremely volatile around major releases. The default is to **keep trading**, because that was the requested behaviour.

To pause new entries around listed events, set in `config.yaml`:

```yaml
trade_news: false
news_blackout_minutes: 30
news_events:
  - time: "2026-08-23T12:30:00+00:00"
    title: US CPI
    impact: high
```

Or pass `--pause-news` on the command line. Open trades are not force-closed by the news filter.

## Layout

```
smc_robot/
  smc/           swings, BOS/CHoCH/MSS, FVG, order blocks, liquidity
  strategy.py    sequential H1 → M15 → M5 algorithm
  risk.py        $100 lot formula, 1:2 RR, breakeven SL
  news.py        optional high-impact blackout
  robot.py       one-position orchestrator
  broker/        paper + MetaTrader 5
config.yaml      editable runtime settings
```
