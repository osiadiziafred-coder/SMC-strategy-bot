# SMC-strategy-bot

MQL5 safety bridge for a Python ML/SMC brain. This Expert Advisor **does not invent BUY/SELL**. Python writes `command.json`; the EA executes, protects, and now **draws Smart Money Concepts on the chart chat**.

## Symbols

XAUUSDm is no longer the default. The EA trades and labels:

| Input | Default name | Common broker aliases |
| --- | --- | --- |
| `InpSymbol1` | **Volatility 75 Index** | `R_75`, `V75`, `VOL75` |
| `InpSymbol2` | **Volatility 50 (1s) Index** | `1HZ50V`, `V50_1s`, `VOL50_1s` |

Attach the EA to either chart on a Deriv (or similar) synthetic MT5 account. If the display name differs, the EA scans Market Watch for a matching alias.

## What appears on the chart chat

The top-left `Comment` panel (and matching chart objects) show:

- Liquidity sweep (SSL / BSL)
- Equal-liquidity sweep extra (clustered EQH/EQL that got swept)
- Order Block
- FVG
- BOS
- CHoCH
- MSS

These overlays are **display only**. Entries still come from Python via `Common\Files\smc_bridge\command.json`.

## Install the EA

1. Copy `PythonML_SMC_Bridge.mq5` (same file as `MQL5/Experts/PythonML_SMC_Bridge.mq5`) into your terminal `MQL5/Experts` folder.
2. Compile in MetaEditor.
3. In Market Watch, show **Volatility 75 Index** and **Volatility 50 (1s) Index**.
4. Attach the EA to one of those charts.
5. Allow DLL/file imports if your terminal asks; the EA reads/writes Common Files only.

## Python command file

Python remains the brain. Example:

```json
{
  "id": "20260905-001",
  "action": "HEARTBEAT",
  "symbol": "Volatility 75 Index"
}
```

`action` may be `HEARTBEAT`, `NONE`, `BUY`, `SELL`, `MODIFY`, or `CLOSE`. `symbol` must resolve to V75 or V50 (1s). One position per symbol. The EA still moves SL to breakeven and trails only after Python is fresh (or `InpProtectIfPythonLost` is on).

Status is written to `Common\Files\smc_bridge\status.json`, including `smc_v75` and `smc_v50_1s` snapshots of the chat labels.

## Tests

```bash
python -m pytest -q
```
