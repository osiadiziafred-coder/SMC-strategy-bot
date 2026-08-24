"""Decision engine: H1 bias → M30 confirmation → liquidity/SMC → M15 entry → score → plan."""

from __future__ import annotations

from smc_robot.config import Settings
from smc_robot.models import Candle, Decision, Direction, Signal, Trend
from smc_robot.risk.protection import Quote
from smc_robot.risk.sizing import SymbolSpec
from smc_robot.risk.trade_plan import build_trade_plan
from smc_robot.scoring import SetupScorer, find_setup_parts
from smc_robot.smc.analyze import analyze_timeframe
from smc_robot.smc.conditions import analyze_conditions
from smc_robot.smc.structure import recent_events


class SmcEngine:
    def __init__(self, settings: Settings, scorer: SetupScorer | None = None):
        self.settings = settings
        self.scorer = scorer or SetupScorer(settings)

    def evaluate(
        self,
        h1: list[Candle],
        m30: list[Candle],
        m15: list[Candle],
        quote: Quote,
        spec: SymbolSpec,
        balance: float,
        recent_spreads: list[float] | None = None,
    ) -> Decision:
        if len(h1) < 30 or len(m30) < 40 or len(m15) < 40:
            return Decision(action="skip", reason="insufficient_bars")

        h1_a = analyze_timeframe(h1, self.settings)
        m30_a = analyze_timeframe(m30, self.settings)
        m15_a = analyze_timeframe(m15, self.settings)
        conditions = analyze_conditions(m15, self.settings, quote.spread_points, recent_spreads)

        if h1_a.trend == Trend.RANGING:
            return Decision(action="skip", reason="h1_ranging")

        direction = Direction.BUY if h1_a.trend == Trend.BULLISH else Direction.SELL
        sweep, order_block, fvg, m30_events = find_setup_parts(
            direction, m30_a, m15_a, self.settings
        )
        m30_confirms = m30_a.trend == h1_a.trend or bool(m30_events)
        if not m30_confirms:
            return Decision(action="skip", reason="m30_no_confirmation")
        if sweep is None:
            return Decision(action="skip", reason="no_recent_liquidity_sweep")
        if order_block is None and fvg is None:
            return Decision(action="skip", reason="no_ob_or_fvg_interaction")

        m15_events = recent_events(
            m15_a.events,
            len(m15_a.candles) - 1,
            self.settings.smc.structure_event_max_age_m15,
            direction,
        )
        if not m15_events:
            return Decision(action="skip", reason="no_m15_structure_confirmation")

        score = self.scorer.score(
            direction, h1_a, m30_a, m15_a, conditions, sweep, order_block, fvg
        )
        if score.total < self.settings.scoring.min_score:
            return Decision(
                action="skip",
                reason=f"score_{score.total:.1f}_below_{self.settings.scoring.min_score}",
                score=score,
            )

        entry = quote.ask if direction == Direction.BUY else quote.bid
        plan = build_trade_plan(
            direction,
            entry,
            sweep,
            order_block,
            fvg,
            conditions.atr,
            balance,
            spec,
            self.settings,
        )
        if plan is None:
            return Decision(action="skip", reason="invalid_trade_plan", score=score)

        signal = Signal(
            direction=direction,
            plan=plan,
            score=score,
            sweep=sweep,
            order_block=order_block,
            fvg=fvg,
            h1_trend=h1_a.trend,
            m30_trend=m30_a.trend,
            m15_trend=m15_a.trend,
            reason="smc_confluence",
        )
        return Decision(action=direction.value.lower(), reason="take_setup", score=score, signal=signal)
