# Session AMD — trading rules implemented by the EA

This note maps the user specification to concrete, testable rules. The Expert Advisor never buys or sells because a candle is green or red. It advances a state machine:

`SESSION RANGE → LIQUIDITY LEVEL → LIQUIDITY SWEEP → MARKET STRUCTURE SHIFT → ENTRY → RISK MANAGEMENT`

## Phases

### Accumulation
During the configured Asia window the EA records open, high, low, close, range size, and bar count. When the window ends, the high and low stay on the chart as buy-side and sell-side liquidity.

A range is rejected when it is too small, too large, or has too few bars. No trades are taken from an invalid range.

### Manipulation
A sweep requires a **pierce** beyond the frozen high or low by `MinSweepPoints` (plus optional buffer). Touching the level is not a sweep.

- Sweep of the high → candidate **SELL**
- Sweep of the low → candidate **BUY**

Price must then return according to `SweepReturnMode` (close back inside the range by default). The EA does not enter on the sweep bar.

If the opposite side of the range is taken **before** that return, the working direction may flip (both sides were engineered). If the first sweep has already rejected, a later take of the other side is treated as the **distribution target**, not a new setup.

### Distribution
After the return, the lower timeframe must confirm:

- Break of a relevant short-term swing (BOS), and/or
- Close through the opposite side of the sweep candle (CISD)
- Optional lower-high / higher-low rejection
- Optional displacement body versus ATR

Only then is an entry armed. Entry style is market, BOS retest, or FVG tap.

## Multi-timeframe

The bot trades **XAUUSDm only** and scans **M15, M30 and H1** in parallel. It takes **one** confirmed AMD setup from whichever of those timeframes is ready (default: first ready). Optional HTF bias still uses the higher timeframe input (default H4) if you turn the bias filter on.

## Stops and targets

- BUY stop: below the manipulation/swing low, plus buffer.
- SELL stop: above the manipulation/swing high, plus buffer.
- If the stop distance is outside `MinSlPoints` / `MaxSlPoints`, or the risk-based lot rounds to zero, the trade is skipped.
- Take profit: fixed RR, next session/swing liquidity, or hybrid (farther of the two). Optional partial at RR then breakeven.

## Quality filters (no entry)

- No valid accumulation range
- No identifiable sweep
- No structure confirmation
- Spread too high
- ATR too high / too low / abnormally expanded
- Stop distance unreasonable
- Max trades or max positions reached
- Outside London/New York (or the sessions you enabled)
- Friday flatten window

## One-trade confirmation

Quality over quantity. After a fill (or a hard skip for impossible risk), the cycle is complete until the next accumulation session starts.
