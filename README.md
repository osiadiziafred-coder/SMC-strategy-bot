# XAUUSDm H1/M5 Market Structure EA

Fully automated MetaTrader 5 Expert Advisor for **XAUUSDm only**. It does not use moving-average crossovers, RSI, or martingale. A trade is opened only when the complete H1 → liquidity/zone → M5 confirmation → structural SL/TP sequence is valid.

## Strategy flow

1. Resolve the broker's exact `XAUUSDm` symbol.
2. Size the position from the **current account balance** (not the original deposit).
3. Read **closed** H1 candles for market structure (HH/HL, LH/LL, BOS, MSS).
4. Map H1 swing liquidity, equal highs/lows, and demand/supply (order-block) zones.
5. Wait for price to reach a relevant H1 area and, by default, a liquidity sweep with rejection.
6. Switch to **M5** and wait for closed-candle confirmation (displacement, BOS/MSS, then a retest into the M5 order block).
7. Place a structural stop beyond invalidation and a take-profit at the next H1 liquidity/structure target.
8. Reject the trade if risk/reward is below the configured minimum (default **1:2**), spread is too wide, or risk limits are hit.
9. Open **one** position per setup, then wait until that trade closes before looking for a new setup.

If the conditions do not align, the EA does nothing.

## Installation

**Easiest (one file):** copy `MQL5/Experts/XAUUSDm_H1M5_SMC.mq5` into MetaEditor.

1. In MT5 press `F4` to open MetaEditor.
2. File → New → Expert Advisor (template) → name it `XAUUSDm_H1M5_SMC`.
3. Delete the template code and paste the full contents of `MQL5/Experts/XAUUSDm_H1M5_SMC.mq5`.
4. Press **Compile** (`F7`). It should report 0 errors.
5. Attach the EA to an **XAUUSDm** chart and enable **Algo Trading**.

**Alternative (modular folder):** copy `MQL5/Experts/XAUUSDm_H1M5_SMC/` into `MQL5/Experts/` and compile `XAUUSDm_H1M5_SMC.mq5` inside that folder.

If XAUUSDm cannot be found, the EA shows an error and will not place trades.

## Balance-based lot size

Default tiers (then continue the same pattern: every extra $100 adds 0.01 lots):

| Account balance | Lot size |
| --- | --- |
| $0 – $149.99 | 0.01 |
| $150 – $249.99 | 0.02 |
| $250 – $349.99 | 0.03 |
| $500 | 0.05 |
| $1,000 | 0.10 |

Examples: $50 → 0.01, $149 → 0.01, $150 → 0.02, $250 → 0.03. After a drawdown the lot size **decreases** with the same table. Lots are then normalized to the broker min/max/step.

Configurable: `StartingLot`, `FirstIncreaseBalance`, `BalanceStep`, `LotIncrease`.

## Important inputs

| Input | Default | Role |
| --- | --- | --- |
| `MaxOpenPositions` | 1 | One position per setup |
| `MinimumRiskReward` | 2.0 | Skip trades with weaker R:R |
| `MaxStopLossPoints` | 5000 | Reject oversized structural stops |
| `MaxSpreadPoints` | 350 | Gold spread filter (broker points) |
| `MaximumDailyLossPercent` | 5.0 | Stop new trades for the day |
| `MaximumDrawdownPercent` | 20.0 | Stop trading after peak-equity drawdown |
| `UseTradingSession` | false | Optional hour window |
| `UseNewsFilter` | false | Left inactive: no news API is bundled |
| `RequireM5Retest` | true | Do not chase the displacement candle |
| `MagicNumber` | 19052601 | Distinguishes this EA's orders |

`MaxStopLossPoints` and `MaxSpreadPoints` are in **broker points** (`SYMBOL_POINT`). On 3-digit gold, 350 points is $0.35; on 2-digit gold it is $3.50. Adjust to your broker.

## Backtesting

Use MT5 Strategy Tester:

- Symbol: the broker's XAUUSDm
- Model: **Every tick based on real ticks** when available
- Try different starting balances ($50, $150, $250, $500, $1,000) and confirm the journal line `Lot size calculated: ...`
- The EA uses closed candles only (bar index 1+) for BOS/MSS/swings, so it is suitable for tester use

Journal examples:

- `No trade: H1 bias unclear`
- `No trade: liquidity sweep not detected`
- `No trade: M5 confirmation missing`
- `No trade: RR below 2.0`
- `No trade: spread too high`
- `BUY setup confirmed` / `BUY order opened`

## Offline checks (this repository)

MetaEditor is required to compile `.ex5`. The repository includes Python checks for the lot table and the structure/liquidity/R:R rules:

```bash
python3 tests/test_strategy.py
python3 tools/verify_ea.py
```

## Files

```
MQL5/Experts/XAUUSDm_H1M5_SMC/
  XAUUSDm_H1M5_SMC.mq5   # inputs, OnInit/OnTick flow
  Types.mqh
  Utils.mqh              # symbol detect, lot size, spread, session
  Structure.mqh          # swings, bias, BOS, MSS, displacement
  Liquidity.mqh          # liquidity, sweeps, demand/supply
  Setups.mqh             # BUY/SELL confirmation, SL/TP/RR
  TradeEngine.mqh        # risk limits, orders, management
  Visual.mqh             # dashboard and chart objects
```
