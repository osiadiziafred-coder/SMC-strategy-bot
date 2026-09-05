# SMC-strategy-bot

MQL5 Expert Advisor for **Volatility 75 Index** and **Volatility 50 (1s) Index**.

The bot **picks a trade only when both pairs print an aligned SMC setup** (same direction). Python `command.json` still works as an override.

## When it trades

A pair has a setup when all of these are present:

- Bias from BOS / CHoCH / MSS
- Liquidity sweep, or **equal-liquidity sweep extra**
- Price tapping an Order Block or FVG
- Confluence score at least `InpMinConfluence` (default 4)

Then:

- If **both** V75 and V50 (1s) have that setup in the **same direction**, the EA sends BUY or SELL on **both** pairs
- One position per symbol, 1:2 RR, then breakeven / trail
- Chart chat shows `TRADE: PICK BUY on both pairs` (or why it is waiting)

Turn the dual-pair gate off with `InpRequireBothPairs=false` if you want each index to fire on its own.

## Symbols

| Input | Default name | Common broker aliases |
| --- | --- | --- |
| `InpSymbol1` | **Volatility 75 Index** | `R_75`, `V75`, `VOL75` |
| `InpSymbol2` | **Volatility 50 (1s) Index** | `1HZ50V`, `V50_1s`, `VOL50_1s` |

`InpLot1` / `InpLot2` at `0` uses each broker's minimum volume.

XAUUSDm is not used.

## Chart chat

The Expert Advisor writes this overlay on the chart (`Comment` panel):

- Liquidity sweep (SSL / BSL)
- Equal-liquidity sweep extra
- Order Block
- FVG
- BOS
- CHoCH
- MSS
- SETUP yes/no and the dual-pair PICK line

## Architecture

Two programs:

1. **Python** (`smc_overlay.py`) — SMC detectors used for tests and chart demos. Optional `command.json` override.
2. **This EA** (`PythonML_SMC_Bridge.mq5`) — detect SMC, show it on chat, pick trades when both pairs align, execute + protect. Never invents a one-sided gold trade.

Files: `Common\Files\smc_bridge\command.json` and `status.json`.

## Install

1. Copy `PythonML_SMC_Bridge.mq5` into `MQL5/Experts`.
2. Compile in MetaEditor.
3. Show both indices in Market Watch.
4. Attach the EA to either chart. AutoTrading must be on.

## Tests

```bash
python -m pytest -q
```
