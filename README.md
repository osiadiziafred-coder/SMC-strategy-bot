# SMC-strategy-bot

MetaTrader 5 Expert Advisor `fredfxV2.mq5` for **XAUUSDm**.

It trades Smart Money Concepts on M5 / M15 / H1: Order Blocks, BOS, MSS, CHoCH, and FVG retests, with H1 bias, 1:2 RR, and trailing stop.

## Install

1. Copy `fredfxV2.mq5` into your MT5 `MQL5/Experts/` folder.
2. Compile it in MetaEditor.
3. Attach it to an **XAUUSDm** chart (any timeframe; the EA reads M5, M15, and H1 itself).
4. Use a **hedging** account. AutoTrading must be enabled.

## Lot sizing (current balance)

Lot size is calculated from the **current account balance**, not the original deposit. After a drawdown it steps back down automatically.

| Account balance | Lot size |
| --- | --- |
| $0 – $149.99 | 0.01 |
| $150 – $249.99 | 0.02 |
| $250 – $349.99 | 0.03 |
| $350 – $449.99 | 0.04 |
| … | +0.01 every extra $100 |

Configurable inputs:

- `StartingLot` = 0.01
- `FirstIncreaseBalance` = 150.00
- `BalanceStep` = 100.00
- `LotIncrease` = 0.01

The result is then clamped to the broker minimum lot, maximum lot, and lot step.

## Defaults

- Symbol: `XAUUSDm`
- Max 3 positions, one per timeframe
- Risk:reward 1:2
- Trail SL to break-even at 1R, then trail
