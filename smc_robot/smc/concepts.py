"""Plain-language definitions of the programmed SMC rules."""

CONCEPTS = {
    "liquidity_sweep": """
LIQUIDITY SWEEP
Price runs stops beyond a confirmed swing, then rejects and closes back inside.

Bullish (sell-side sweep):
  1. A confirmed swing low is the pool (sell-side liquidity).
  2. A later bar prints low BELOW that pool (stops are taken).
  3. The same bar CLOSES back ABOVE the pool (rejection).
  A close that stays below the pool is a break, not a sweep.

Bearish (buy-side sweep):
  1. Confirmed swing high is the pool.
  2. Bar prints high ABOVE the pool.
  3. Same bar CLOSES back BELOW the pool.

The robot uses the sweep wick as the first SL candidate.
""",
    "equal_liquidity_sweep": """
EQUAL-LIQUIDITY SWEEP (extra)
Equal highs or equal lows are a stronger pool than a single swing.

Rule:
  Two or more swing highs (or lows) within 0.15 × ATR of each other
  form one equal-liquidity pool. Price is the cluster mean.

When a sweep hits that clustered pool:
  - equal_liquidity = true
  - members >= 2
  - extra score: +equal_liquidity_extra (default +5)
  - extra +2 if the pool is an EXTERNAL swing (HTF liquidity)

This is the "equal-liquidity sweep extra" — not a different entry type,
but a higher-quality version of the same sweep.
""",
    "order_block": """
ORDER BLOCK (OB)
The last opposite-body candle before a valid BOS or MSS, only if displacement
is strong enough.

Bullish OB: last down-close candle before a bullish BOS/MSS.
  Zone = [that candle low, that candle high]. Demand.

Bearish OB: last up-close candle before a bearish BOS/MSS.
  Zone = [low, high]. Supply.

Filters:
  Impulse from OB close to the break close >= 1.2 × ATR(14).
  Invalidated when a later bar CLOSES through the far side of the zone.
  Age cap (default 24 bars) for new entries.
  A tap (overlap without a closing break) is the intended interaction.
""",
    "fvg": """
FAIR VALUE GAP (FVG)
A three-candle imbalance. The middle candle displaces so hard that candle 1
and candle 3 do not overlap.

Bullish FVG at bar i:
  low[i] > high[i-2]
  zone = [high[i-2], low[i]]

Bearish FVG at bar i:
  high[i] < low[i-2]
  zone = [high[i], low[i-2]]

Minimum size: 0.10 × ATR(14). Tiny gaps are ignored.
Filled / dead when price fully trades through the zone.
Partial fill stays valid until the far side is taken.
Entry needs current bar overlap and close still on the correct side.
""",
    "bos": """
BOS — BREAK OF STRUCTURE (continuation)
Trend continues. Breaks use candle CLOSE only, never a wick.

Bullish BOS: trend is already BULLISH and close > last confirmed INTERNAL swing high.
Bearish BOS: trend is already BEARISH and close < last confirmed INTERNAL swing low.

Internal swings use n=2. The swing must be confirmed (n bars on both sides)
before it can be broken. Tiny inside bars are not BOS.
""",
    "choch": """
CHOCH — CHANGE OF CHARACTER (first reversal warning)
The first internal break against the current trend. Not an automatic entry.

Bullish CHoCH: trend is BEARISH and close > last confirmed INTERNAL swing high.
Bearish CHoCH: trend is BULLISH and close < last confirmed INTERNAL swing low.

CHoCH is confirmation, not a standalone trigger. Weak / random CHoCH
does not fire a trade without sweep + OB/FVG + H1/M30 + ML.
""",
    "mss": """
MSS — MARKET STRUCTURE SHIFT (external reversal)
A larger shift: close beyond the last confirmed EXTERNAL swing against the trend.

Bullish MSS: trend is BEARISH and close > last confirmed EXTERNAL swing high (n=5).
Bearish MSS: trend is BULLISH and close < last confirmed EXTERNAL swing low.

On one bar the priority is MSS > CHoCH > BOS.
MSS carries the heaviest structure weight in scoring and ML features.
""",
}


def render_concepts(names: list[str] | None = None) -> str:
    keys = names or list(CONCEPTS)
    return "\n".join(CONCEPTS[k].strip() + "\n" for k in keys if k in CONCEPTS)
