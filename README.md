# SMC-strategy-bot

MQL5 Expert Advisor for **Volatility 75 Index** and **Volatility 50 (1s) Index**.

The bot **picks a trade only when both pairs print an aligned A+ SMC setup** (skill 85+, same direction). Python `command.json` still works as an override.

## When it trades

A pair has an A+ setup when all of these are present (pro skill mode, default on):

- HTF bias matches entry TF (H1 on V75, M5 on V50 1s)
- Buy only in **discount**, sell only in **premium**
- Liquidity sweep, then **CHoCH/MSS after the sweep** (not before)
- Displacement candle on that CHoCH/MSS
- Price tapping an unmitigated Order Block or FVG
- Market is trending (efficiency ratio), not chop
- Skill score at least `InpMinSkillScore` (default **85**)
- Dual-pair same direction

Then:

- BUY or SELL on **both** pairs
- Risk `InpRiskPercent` of balance (default 0.5%)
- One position per symbol, 1:2 RR, then breakeven / trail
- Hard stop if daily loss hits 3% or 4 trades are already taken
- Chart chat shows `SKILL: 91/100 PASS` or what is still missing

Turn the dual-pair gate off with `InpRequireBothPairs=false` if you want each index to fire on its own.

## Symbols

| Input | Default name | Common broker aliases |
| --- | --- | --- |
| `InpSymbol1` | **Volatility 75 Index** | `R_75`, `V75`, `VOL75` |
| `InpSymbol2` | **Volatility 50 (1s) Index** | `1HZ50V`, `V50_1s`, `VOL50_1s` |

`InpLot1` / `InpLot2` at `0` uses each broker's minimum volume.

XAUUSDm is not used.

**85 is a skill score, not a win-rate promise.** The checklist filters junk. Demo it before any real size.

## Chart chat

The Expert Advisor writes this overlay on the chart (`Comment` panel):

- Liquidity sweep (SSL / BSL)
- Equal-liquidity sweep extra
- Order Block
- FVG
- BOS
- CHoCH
- MSS
- SKILL xx/100 PASS or WAIT, and what is missing
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
