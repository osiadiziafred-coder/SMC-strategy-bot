from __future__ import annotations

from smc_robot.config import RobotConfig


STRATEGY_SUMMARY = """
FredFx v1 SMC
=============

This is FredFx v1 SMC, a Python Smart Money Concepts robot for XAUUSDm (gold).
It is not financial advice. Gold is leveraged; you can lose more than you deposit.

How a trade is picked (all gates must pass)
-------------------------------------------
1. H1 sets bullish or bearish market structure from the latest BOS, CHoCH, or MSS.
2. M15 must confirm that bias and also show a liquidity zone plus an unmitigated
   order block or fair value gap.
3. M5 waits for a liquidity sweep, then a same-direction MSS / CHoCH / BOS,
   then a fresh tap of an unmitigated order block or FVG.
4. Only then does the robot open exactly one position.
5. Stop loss sits behind the sweep wick and the entry zone. Take profit is 2x
   that distance (1:2).
6. When price moves +1R in favor, SL is moved to breakeven.
7. After the trade closes, the robot may take another valid setup the same day.

A single concept is never enough. Isolated BOS, FVG, or a lone sweep is ignored.

Rules
-----
- Market:           XAUUSDm
- Timeframes:       H1 (bias) → M15 (liquidity + OB/FVG + structure) → M5 (entry)
- Concepts:         Order blocks, BOS, MSS, CHoCH, FVG, liquidity sweep, liquidity zones
- Positions:        1 open trade at a time
- Frequency:        Multiple trades per day after the previous one closes
- News:             Configurable (default: trade through news)
- Stop : target:    1 : 2
- Trade management: At +1R, move SL to breakeven
- Lots:             0.01 lot for every $100 of balance
""".strip()


def render_summary(config: RobotConfig | None = None) -> str:
    cfg = config or RobotConfig()
    news = "trades through news" if cfg.trade_news else f"pauses {cfg.news_blackout_minutes} minutes around listed news"
    return "\n".join(
        [
            f"Robot: {cfg.robot_name}",
            f"Symbol: {cfg.symbol}",
            f"Timeframes: {' → '.join(cfg.timeframes)}",
            f"Risk:reward: 1:{cfg.risk_reward:.0f}",
            f"Lot rule: 0.01 per $100 (min {cfg.min_lot})",
            f"Max open positions: {cfg.max_open_positions}",
            f"News filter: {'off' if cfg.trade_news else 'on'} ({news})",
            f"SL management: move to breakeven at +{cfg.breakeven_at_r:.0f}R",
            f"H1 → M15 → M5 gates: all required",
            f"Liquidity sweep required: {cfg.require_liquidity_sweep}",
            f"M15 liquidity zone required: {cfg.require_m15_liquidity}",
            f"M15 OB/FVG required: {cfg.require_m15_pd_array}",
            f"M5 structure after sweep required: {cfg.require_m5_structure_after_sweep}",
            "",
            STRATEGY_SUMMARY,
        ]
    )
