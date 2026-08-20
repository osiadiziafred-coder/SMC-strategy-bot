from __future__ import annotations

from smc_robot.config import RobotConfig


STRATEGY_SUMMARY = """
FredFx V1 m5
============

This is FredFx V1 m5, a Python Smart Money Concepts robot for XAUUSDm (gold).
It is not financial advice. Gold is leveraged; you can lose more than you deposit.

How it trades
-------------
1. H1 sets the bias from the latest BOS, CHoCH, or MSS.
2. M15 must agree (recent structure in the same direction).
3. M5 looks for a liquidity sweep (stop hunt of a swing high/low).
4. After the sweep, it waits for a tap of an unmitigated order block or FVG.
5. It opens exactly one position. SL:TP is 1:2.
6. When price moves +1R in favor, SL (XL) is moved to breakeven.
7. After that trade closes, it may take another the same day — including through news.

Rules
-----
- Market:           XAUUSDm
- Timeframes:       M5 (entry), M15 (structure), H1 (bias)
- Concepts:         Order blocks, BOS, MSS, CHoCH, FVG, liquidity sweep
- Positions:        1 open trade at a time
- Frequency:        Multiple trades per day after the previous one closes
- News:             Trades through news (no news pause)
- Stop : target:    1 : 2
- Trade management: At +1R, move SL to breakeven
- Lots:             Any starting balance. Every $100 adds 0.01 lot (minimum 0.01)
""".strip()


def render_summary(config: RobotConfig | None = None) -> str:
    cfg = config or RobotConfig()
    news = "trades through news" if cfg.trade_news else "pauses around news"
    return "\n".join(
        [
            f"Robot: {cfg.robot_name}",
            f"Symbol: {cfg.symbol}",
            f"Timeframes: {', '.join(cfg.timeframes)}",
            f"Risk:reward: 1:{cfg.risk_reward:.0f}",
            f"Lot rule: 0.01 per $100 (start any amount, min {cfg.min_lot})",
            f"Max open positions: {cfg.max_open_positions}",
            f"News filter: off ({news})" if cfg.trade_news else f"News filter: on ({news})",
            f"SL management: move to breakeven at +{cfg.breakeven_at_r:.0f}R",
            f"Liquidity sweep required: {cfg.require_liquidity_sweep}",
            "",
            STRATEGY_SUMMARY,
        ]
    )
