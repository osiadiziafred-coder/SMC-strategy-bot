# Python AI SMC Robot (XAUUSDm / MT5)

Python Smart Money Concepts robot for **XAUUSDm**. Python analyzes H1 / M30 / M15, scores the setup, and MetaTrader 5 executes. The robot trades through news and relies on spread, slippage, and quote-age protection instead of a news calendar.

## Programmable SMC rules

Breaks use **candle close only**, never a wick. Swings are confirmed only after `n` bars exist on both sides (no repaint).

| Concept | Rule |
|---|---|
| **Swing high / low** | Bar `i` is a swing high if its high is strictly greater than the `n` bars on each side (`n=2` internal, `n=5` external). Inverse for swing lows. |
| **Trend** | Last two *external* swing highs and lows: HH+HL = bullish, LH+LL = bearish, otherwise ranging. |
| **BOS** | Continuation: bullish trend and close above last confirmed *internal* swing high (inverse for sell). |
| **CHoCH** | First reversal warning: bearish trend and close above last confirmed *internal* swing high (inverse for sell). |
| **MSS** | External reversal: bearish trend and close above last confirmed *external* swing high (inverse for sell). On one bar, MSS > CHoCH > BOS. |
| **Order block** | Last opposite-body candle before a BOS/MSS, only if the displacement is ≥ `1.2 × ATR(14)`. Bullish OB is invalidated by a close below its low. |
| **FVG** | Three-candle gap: bullish if `low[i] > high[i-2]`. Valid while not fully traded through. Minimum size `0.10 × ATR`. |
| **Liquidity sweep** | Sell-side sweep (buy catalyst): low trades below a confirmed swing low and the bar closes back above it. Inverse for buy-side. Equal highs/lows within `0.15 × ATR` are stronger pools. |

Entry sequence: **H1 bias → M30 confirmation → liquidity sweep → M15 OB/FVG tap + structure event → score ≥ 70 → order**.

## Risk and execution

- SL is taken from the setup (sweep wick, OB, or FVG), not a fixed point distance. TP is **1:2**.
- Lot size: every **$100** of balance adds **0.01** lots, then snapped to the broker min / step / max.
- Maximum **1** open position. After it closes, the next valid setup can be taken the same day.
- At **+1R**, SL is moved to breakeven. TP stays at +2R.
- Orders are blocked when spread exceeds the cap, spikes versus the recent median, the quote is stale, or slippage protection would be exceeded. High-impact news is **not** auto-filtered.

## Run

```bash
pip install -r requirements.txt
cp .env.example .env   # set MT5_LOGIN / MT5_PASSWORD / MT5_SERVER on Windows
python -m smc_robot --mode dry    # MT5 data, no orders
python -m smc_robot --mode live   # MT5 execution
python -m smc_robot --mode paper  # in-memory broker
pytest
```

Live mode needs the `MetaTrader5` package on Windows with a running MT5 terminal. Linux CI uses the paper broker and the SMC unit tests.

Config lives in `config/default.yaml`.
