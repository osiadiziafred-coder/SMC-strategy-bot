# SMC Scalper EA

MetaTrader 5 Expert Advisor that scalps **Volatility 100 (1s)**, **Volatility 75 (1s)**, and **XAUUSD** with a simple Smart Money / price-action pipeline:

**M5 trend → liquidity sweep → M1 BOS/MSS → entry → stop loss → dynamic breakeven → lock profit → take profit**

This is not a high-frequency tick scalper. It waits until trend, sweep, and confirmation agree, then manages the trade.

> Trading involves substantial risk of loss. This EA is provided as-is for education and testing. Demo-test it thoroughly before any live account. Past structure on a chart does not guarantee future results.

## Strategy

### 1. M5 market bias

Swing highs and lows are confirmed with a fractal-style lookback (default 3 bars each side).

| M5 structure | Allowed direction |
| --- | --- |
| Higher highs **and** higher lows | BUY setups only |
| Lower highs **and** lower lows | SELL setups only |
| Mixed / ranging | No new trades |

### 2. Liquidity

Recent M5 swing highs are buy-side liquidity. Recent M5 swing lows are sell-side liquidity.

The EA waits for a **sweep**: price wicks through the pool and closes back inside (default: the last closed M1 candle).

- Uptrend: sweep of a low (SSL) for a buy setup
- Downtrend: sweep of a high (BSL) for a sell setup

### 3. M1 confirmation

After the sweep it waits for a **fresh** M1 close through the nearest opposing M1 swing (BOS / MSS). It does not chase a break that already happened several bars ago.

### 4. Entry

Default mode waits for a **small pullback** into the confirmation impulse (33% retrace). If the pullback never comes, it can enter at market while the setup is still valid, or skip — that is configurable.

A trade is sent only when **trend + sweep + BOS/MSS** all agree.

### 5. Stop loss

SL is placed beyond the swept swing (the invalidation) plus an ATR buffer.

### 6. Dynamic breakeven and lock-in

As the trade moves into profit the stop is advanced:

| Profit | Stop |
| --- | --- |
| +1 step | Breakeven (plus a tiny offset for commission/spread) |
| +2 steps | Lock 1 step of profit |
| +3 steps | Lock 2 steps |
| +4 steps | Lock 3 steps |

Default distances are **ATR-based** so the same logic works on gold and on Deriv volatility indices. You can switch to raw points if you prefer.

### 7. Take profit

Choose one:

- Fixed R:R (default 1:2)
- Next opposing M5 liquidity pool
- **Nearest of the two** (default)

Trades with projected R:R below `MinRewardRatio` are skipped.

### 8. Risk management

- Risk % of equity per trade (or a fixed lot if risk is 0)
- Max open trades (global and per symbol)
- Max trades per day
- Daily loss pause (optional flatten)
- Spread filter
- Slippage / deviation on the order
- Cooldown after a trade
- Each liquidity swing is consumed once (no repeat entries on the same pool)
- Optional session filter (server time)

## Install in MetaTrader 5

1. Open MT5 → **File → Open Data Folder**.
2. Copy `MQL5/Experts/SMC_Scalper_EA.mq5` into `MQL5/Experts/`.
3. Restart MT5 (or right-click Navigator → Refresh).
4. Open MetaEditor, open the file, press **Compile**. Fix nothing if it builds with 0 errors.
5. Enable **Algo Trading** on the toolbar.
6. Attach the EA to each chart you want it to trade:

| Instrument | Typical Deriv / broker name |
| --- | --- |
| Gold | `XAUUSD` |
| Vol 100 (1s) | `Volatility 100 (1s) Index` |
| Vol 75 (1s) | `Volatility 75 (1s) Index` |

Use **M1** on the chart (the EA still reads M5 internally). Allow live trading in the Common tab.

If your broker uses a slightly different symbol name, add it to **Allowed symbols** or disable **Restrict to list**.

Attach **one instance per symbol**. Use the same magic number so daily loss and max-trades apply across all three.

## Suggested starting inputs

These are conservative starting points for demo testing, not a promise of profit.

| Input | Suggested start | Why |
| --- | --- | --- |
| Risk percent | `0.3` – `0.5` | Volatility 1s indices can move fast |
| Max open trades | `3` | One per symbol |
| Max per symbol | `1` | No stacking the same idea |
| Daily loss percent | `2` – `3` | Hard stop for a bad day |
| Distance mode | ATR | Same logic on gold and synthetics |
| TP mode | Nearest | Bank liquidity if it is closer than 1:2 |
| Entry mode | Pullback | Avoids chasing the BOS close |
| Max spread | Broker-specific | Set after you watch typical spread |

Gold often needs a session filter if your broker’s XAUUSD spread explodes overnight. Volatility indices on Deriv trade around the clock; leave the session filter off.

## How to tell it is working

The chart comment shows:

- M5 bias (buy-only / sell-only / range)
- State: scan → wait sweep → wait BOS/MSS → wait pullback
- Spread, daily P/L, open trade count

Optional lines:

- Orange dotted — latest M5 high (liquidity)
- Blue dotted — latest M5 low (liquidity)
- Gold dashed — swept level
- Lime dashed — M1 BOS/MSS level

Experts log prints sweep, confirmation, entries, and skipped trades.

## Backtest notes

- Use **every tick** or **1-minute OHLC** at minimum. Open-price mode will miss sweeps and wicks.
- Test each symbol separately, then a demo period with all three charts live.
- Synthetic 1-second indices are noisy; if you get too many trades, raise `Min impulse ATR` and `Swing strength`.

## File

```
MQL5/Experts/SMC_Scalper_EA.mq5
```

Single-file EA on purpose: copy one file into `Experts` and compile. No extra include folders.
