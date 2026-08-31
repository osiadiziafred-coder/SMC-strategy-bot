"""Hybrid pipeline: H1 → M30 → sweep → OB/FVG → M15 structure → ML → risk."""

from __future__ import annotations

from smc_robot.bridge import new_command_id
from smc_robot.config import Settings
from smc_robot.models import Candle, Decision, Direction, Signal, Trend
from smc_robot.risk.protection import Quote
from smc_robot.risk.sizing import SymbolSpec
from smc_robot.risk.trade_plan import build_trade_plan
from smc_robot.scoring import SetupScorer, find_setup_parts, nearest_opposing_liquidity
from smc_robot.smc.analyze import analyze_timeframe
from smc_robot.smc.conditions import analyze_conditions
from smc_robot.smc.news import news_block_reason
from smc_robot.smc.premium_discount import favors_setup, structure_premium_discount
from smc_robot.smc.sessions import session_allowed
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

        ok_session, session_name = session_allowed(m15[-1].time, self.settings.sessions)
        if not ok_session:
            return Decision(action="skip", reason=session_name)

        news_reason = news_block_reason(m15[-1].time, self.settings.news)
        if news_reason:
            return Decision(action="skip", reason=news_reason)

        if h1_a.trend == Trend.RANGING:
            return Decision(action="skip", reason="h1_ranging")

        direction = Direction.BUY if h1_a.trend == Trend.BULLISH else Direction.SELL
        pd = structure_premium_discount(
            m15_a.candles,
            h1_a.external_swings,
            direction,
            self.settings.smc.discount_max,
            self.settings.smc.premium_min,
        )
        conditions.premium_discount = pd
        if self.settings.smc.require_premium_discount and not favors_setup(pd, direction):
            return Decision(action="skip", reason="premium_discount_mismatch")

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

        if self.settings.scoring.require_ml and self.scorer._model is None:
            return Decision(action="skip", reason="ml_model_unavailable")

        opposite = Direction.SELL if direction == Direction.BUY else Direction.BUY
        opp_sweep, opp_ob, opp_fvg, _ = find_setup_parts(opposite, m30_a, m15_a, self.settings)
        opp_features = self.scorer.score(
            opposite, h1_a, m30_a, m15_a, conditions, opp_sweep, opp_ob, opp_fvg
        )
        score = self.scorer.score(
            direction,
            h1_a,
            m30_a,
            m15_a,
            conditions,
            sweep,
            order_block,
            fvg,
            opposite_probability=opp_features.ml_probability,
        )
        if direction == Direction.BUY:
            score.ml_buy_probability = score.ml_probability
            score.ml_sell_probability = opp_features.ml_probability
        else:
            score.ml_sell_probability = score.ml_probability
            score.ml_buy_probability = opp_features.ml_probability
        if (
            score.ml_probability is not None
            and score.ml_probability < self.settings.scoring.ml_min_probability
        ):
            return Decision(
                action="skip",
                reason=f"ml_probability_{score.ml_probability:.2f}_below_{self.settings.scoring.ml_min_probability}",
                score=score,
            )
        if (
            score.ml_probability is not None
            and opp_features.ml_probability is not None
            and opp_features.ml_probability >= score.ml_probability
        ):
            return Decision(
                action="skip",
                reason=(
                    f"ml_conflict_buy_{score.ml_buy_probability:.2f}"
                    f"_sell_{score.ml_sell_probability:.2f}"
                ),
                score=score,
            )
        if score.grade.value not in self.settings.scoring.allowed_grades:
            return Decision(
                action="skip",
                reason=f"setup_grade_{score.grade.value}_not_allowed",
                score=score,
            )
        if score.total < self.settings.scoring.min_score:
            return Decision(
                action="skip",
                reason=f"score_{score.total:.1f}_below_{self.settings.scoring.min_score}",
                score=score,
            )

        entry = quote.ask if direction == Direction.BUY else quote.bid
        obstacle = nearest_opposing_liquidity(m15_a, direction, entry)
        if obstacle is None:
            obstacle = nearest_opposing_liquidity(m30_a, direction, entry)
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
            opposing_liquidity=obstacle,
        )
        if plan is None:
            return Decision(action="skip", reason="invalid_trade_plan", score=score)

        raw = f"{self.settings.symbol}:{direction.value}:{m15[-1].time.isoformat()}"
        signal_id = new_command_id("trade", when=m15[-1].time, salt=raw)
        signal = Signal(
            signal_id=signal_id,
            direction=direction,
            plan=plan,
            score=score,
            sweep=sweep,
            order_block=order_block,
            fvg=fvg,
            h1_trend=h1_a.trend,
            m30_trend=m30_a.trend,
            m15_trend=m15_a.trend,
            reason="smc_ml_confluence",
            grade=score.grade,
        )
        return Decision(action=direction.value.lower(), reason="take_setup", score=score, signal=signal)
