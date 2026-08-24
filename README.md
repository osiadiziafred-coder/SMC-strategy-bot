# SMC Strategy Bot — Session AMD Expert Advisor

MetaTrader 5 Expert Advisor that trades the **Accumulation → Manipulation → Distribution** (AMD / ICT Power of 3) session model.

Price is not treated as a random up/down stream. The EA first maps the overnight range, waits for a real liquidity sweep of that range, then requires a market-structure shift before it will enter the distribution leg.

![AMD cycle example](docs/amd_cycle_example.png)

## Strategy in one sequence

1. **Accumulation (Asia)** — build and freeze the session high/low, range, and resting liquidity.
2. **Manipulation (typically London)** — wait for price to actually pierce buy-side or sell-side liquidity. A touch of the level is not a trade.
3. **Confirmation** — rejection back inside/through the level, then a lower-timeframe break of structure / CISD.
4. **Distribution** — enter with HTF bias agreement, SL beyond the sweep extreme, TP by risk/reward and/or the next liquidity pool.
5. **One cycle, one idea** — after a valid setup is taken (or rejected for risk), wait for the next accumulation session.

The EA does **not** assume that every session high or low will be swept, and it does **not** enter on a sweep without confirmation.

## Install in MetaTrader 5 (one file)

The full bot is **`AMD_Session_EA.mq5`**. Copy that one file into `MQL5/Experts/` (or copy `MQL5/Experts/AMD_Session_EA.mq5` plus `MQL5/Include/AMD/`).

1. Open an **XAUUSDm** chart. The EA will refuse any other symbol.
2. MT5 → **File → Open Data Folder** → `MQL5/Experts/` → paste `AMD_Session_EA.mq5`.
3. Compile (F7). Enable **Algo Trading**. Attach the EA.
4. The dashboard is a navy header plus light-blue rows with **black text**. It is built from read-only chart fields so a white chart background cannot hide it. Set theme to Dark only if you use a black chart.

The bot scans **H1, M30 and M15** and takes **one** confirmed setup from whichever of those timeframes is ready first. It opens **one position**. Lots start at **0.01** and add **0.01 per $100** of account balance (input `InpBalancePerLot`).

The EA reads those timeframes from the symbol history. You can attach it to any of M15 / M30 / H1.

## Default session map (server time)

| Session | Default window | Role |
| --- | --- | --- |
| Asia | 00:00 – 08:00 | Accumulation range |
| London | 08:00 – 12:00 | Manipulation / Judas swing (entries allowed) |
| New York | 12:00 – 17:00 | Distribution continuation (entries allowed) |

## What must be true before a trade

**BUY**

1. Accumulation range is valid.
2. Price sweeps **below** the range low (sell-side liquidity).
3. Price fails and closes back inside/through that low.
4. Bullish structure confirms (BOS / CISD, optional rejection + displacement).
5. HTF bias filter agrees (if enabled).
6. Spread, ATR, session, SL-distance, and trade-count filters pass.
7. SL is placed below the manipulation low. TP uses RR, liquidity, or hybrid.

**SELL** — the inverse against the accumulation high.

A bar that only tags the Asia high/low is ignored. A sweep that never confirms is ignored. Taking the opposite side of the range **after** a rejected sweep is treated as the distribution target, not as a new opposite setup.

## Inputs (all strategy parameters)

Every behaviour below is an EA input. You do not need to edit source to change it.

### General
- Magic number, order comment, allow BUY, allow SELL
- Evaluate on new LTF bar only
- Debug journal prints

### Sessions
- Asia / London / New York start and end (hour + minute)
- Trade during London, trade during New York
- Flatten on Friday from a chosen hour

### Timeframes and structure
- Higher timeframe (bias), lower timeframe (sweeps / MSS / entry)
- HTF / LTF lookback
- Fractal swing strength
- Equal high/low lookback and tolerance
- HTF bias mode: off / with-trend / counter-trend

### Accumulation and sweep
- Min / max range size (points)
- Minimum bars inside accumulation
- Minimum pierce beyond the level, extra buffer
- Sweep return rule: close inside range / through the level / wick only
- Require LH/HL rejection
- Confirmation: BOS, CISD, or both
- Optional displacement candle vs ATR

### Entry
- Market on confirmation, retest of BOS, or FVG tap
- Max bars after MSS, max retest wait, minimum FVG size

### Risk
- Balance-scale lots (default): start at 0.01, add 0.01 per $100 balance, or fixed lots / % of balance
- Max lot cap
- One open position at a time
- SL buffer beyond the sweep extreme
- Min / max SL distance (skip the trade if the stop is unreasonable)
- TP mode: risk/reward, next liquidity, or hybrid
- RR multiple (use 1.5 / 2 / 3 / 4 as you prefer)
- Partial close % at a first RR target, then move SL to breakeven
- Max trades per day, max open positions, one trade per AMD cycle

### Filters
- Max spread
- Min / max ATR
- Skip abnormally high ATR vs its average

### Visuals
- Accumulation box, session high/low, BSL/SSL labels
- Manipulation zone, MSS arrow, FVG, entry / SL / TP
- On-chart dashboard (high-contrast rows: session, H1/M30/M15 phase, bias, range, next lot, last message)

## Chart objects

Prefix `AMD_`. The dashboard shows the live phase:

`IDLE → ACCUMULATION → RANGE SET → MANIPULATION → CONFIRMATION → IN TRADE / CYCLE COMPLETE`

Invalid ranges are marked `RANGE INVALID` and are not traded.

## Python decision engine (no MT5 required)

`python/amd_engine.py` is a rules-faithful port of the EA core. It is used to unit-test the model.

```bash
python3 -m unittest tests.test_amd_engine -v
python3 python/visualize_amd.py
```

The visualiser writes `docs/amd_cycle_example.png`.

## Risk notice

This is a rules-based automation of a discretionary SMC/ICT concept. It is **not** financial advice. Demo-test on your broker’s server time, spread, and symbol digits before any live use. Past synthetic tests do not predict live results.

## Repository layout

```
AMD_Session_EA.mq5                # FULL standalone bot — copy this one file into MT5
MQL5/Experts/AMD_Session_EA.mq5   # same standalone bot
MQL5/Include/AMD/                 # optional split modules (not required to compile)
python/amd_engine.py              # testable decision core
python/visualize_amd.py
tests/test_amd_engine.py
docs/amd_cycle_example.png
```
