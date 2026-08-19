"""Main SMC robot: scan M5/M15/H1, open up to 3 trades, trail SL up."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from smc_robot.broker.base import Broker, Position
from smc_robot.config import RobotConfig
from smc_robot.risk import lot_size, stops_for_entry, trail_stop
from smc_robot.signals import TradeSetup, scan_setups

logger = logging.getLogger(__name__)


@dataclass
class RobotReport:
    opened: list[Position] = field(default_factory=list)
    trailed: list[tuple[int, float]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    setups: list[TradeSetup] = field(default_factory=list)


class SMCRobot:
    def __init__(self, broker: Broker, config: RobotConfig | None = None) -> None:
        self.broker = broker
        self.config = config or RobotConfig()
        self._trades_today = 0
        self._day_key: str | None = None
        self._breakeven: dict[int, bool] = {}

    def step(self, frames: dict[str, pd.DataFrame] | None = None) -> RobotReport:
        """One scan of the three timeframes: manage XL, then look for entries."""
        self._rollover_day()
        report = RobotReport()
        self._trail_open_positions(report)

        account = self.broker.account()
        open_pos = account.open_positions
        if len(open_pos) >= self.config.max_positions:
            report.skipped.append("max 3 positions already open")
            return report

        if frames is None:
            frames = {
                tf: self.broker.candles(tf)
                for tf in self.config.timeframes
            }

        setups = scan_setups(frames, self.config)
        report.setups = setups
        used_tfs = {p.timeframe for p in open_pos}
        volume = lot_size(account.balance, self.config)

        for setup in setups:
            if len(self.broker.account().open_positions) >= self.config.max_positions:
                report.skipped.append("hit max positions while filling")
                break
            if not self.config.allow_multiple_trades_per_day and self._trades_today > 0:
                report.skipped.append("already traded today")
                break
            if self._trades_today >= self.config.max_trades_per_day:
                report.skipped.append("daily trade cap")
                break
            if self.config.one_position_per_timeframe and setup.timeframe in used_tfs:
                report.skipped.append(f"{setup.timeframe} already has a position")
                continue
            if volume <= 0:
                report.skipped.append("lot size is 0")
                break

            bid, ask = self.broker.bid_ask()
            fill = ask if setup.side == "buy" else bid
            sl, tp = stops_for_entry(
                setup.side, fill, setup.sl, self.config.risk_reward
            )
            position = self.broker.open_trade(
                side=setup.side,
                volume=volume,
                sl=sl,
                tp=tp,
                timeframe=setup.timeframe,
                comment=f"SMC {setup.timeframe} {setup.event_kind}",
            )
            used_tfs.add(setup.timeframe)
            self._trades_today += 1
            report.opened.append(position)
            logger.info(
                "opened %s %s vol=%.2f entry=%.2f sl=%.2f tp=%.2f score=%s (%s)",
                setup.side,
                setup.timeframe,
                volume,
                position.entry,
                position.sl,
                position.tp,
                setup.score,
                setup.reason,
            )
        return report

    def _trail_open_positions(self, report: RobotReport) -> None:
        bid, ask = self.broker.bid_ask()
        for pos in self.broker.account().open_positions:
            price = bid if pos.side == "buy" else ask
            new_sl, now_be = trail_stop(
                side=pos.side,
                entry=pos.entry,
                current_sl=pos.sl,
                current_price=price,
                original_risk=pos.original_risk,
                config=self.config,
                already_breakeven=self._breakeven.get(pos.ticket, False),
            )
            self._breakeven[pos.ticket] = now_be
            if (pos.side == "buy" and new_sl > pos.sl) or (
                pos.side == "sell" and new_sl < pos.sl
            ):
                self.broker.modify_sl(pos.ticket, new_sl)
                pos.sl = new_sl
                report.trailed.append((pos.ticket, new_sl))
                logger.info("trailed XL ticket=%s new_sl=%.2f", pos.ticket, new_sl)

    def _rollover_day(self) -> None:
        key = datetime.now(timezone.utc).date().isoformat()
        if self._day_key != key:
            self._day_key = key
            self._trades_today = 0


def strategy_summary(config: RobotConfig | None = None) -> str:
    cfg = config or RobotConfig()
    return f"""
SMC XAUUSDM Robot — strategy summary
====================================
Symbol            : {cfg.symbol}
Timeframes        : {", ".join(cfg.timeframes)}
HTF bias          : {cfg.htf_bias} BOS / MSS direction
Entries           : up to {cfg.max_positions} positions (one per M5, M15, H1)
Concepts          : Order Blocks, BOS, MSS, CHoCH, FVG
Risk : Reward     : 1 : {cfg.risk_reward:g}  (SL distance × {cfg.risk_reward:g} = TP)
Lot sizing        : any starting balance trades {cfg.min_lot} lot;
                    every extra $300 of balance adds {cfg.lot_per_300_usd} lot
                    ($300=0.01, $600=0.02, $900=0.03 …)
Trailing XL (SL)  : when trade reaches {cfg.trail_activate_r:g}R profit,
                    move SL to breakeven, then trail SL *up* with price
                    (down on sells). SL never moves against the trade.
News              : {"trades through news" if cfg.trade_news else "block news windows"}
Multiple / day    : {"yes" if cfg.allow_multiple_trades_per_day else "no"}
                    (cap {cfg.max_trades_per_day} trades/day)

How a trade is picked
---------------------
1. H1 defines bullish or bearish bias from the latest BOS / MSS.
2. M5, M15, and H1 each look for CHoCH or MSS in that same direction.
3. Displacement must leave an unmitigated Order Block and/or FVG.
4. Entry is a retest of that OB or FVG (price trading back into the zone).
5. SL sits beyond the zone; TP is 2× that risk. Confluence score must be
   at least {cfg.min_confluence_score}.
6. As soon as price moves in profit, the robot walks SL up (XL adjust).
""".strip()
