from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from smc_robot.models import Decision, DecisionRecord


class DecisionJournal:
    def __init__(self, log_dir: str):
        self.path = Path(log_dir)
        self.path.mkdir(parents=True, exist_ok=True)
        self.file = self.path / "decisions.jsonl"

    def write(self, symbol: str, decision: Decision, quote_spread: float = 0.0) -> DecisionRecord:
        record = self._record(symbol, decision, quote_spread)
        self._append(record)
        return record

    def write_outcome(
        self,
        symbol: str,
        decision: Decision,
        *,
        result: str,
        quote_spread: float = 0.0,
        rejection_reason: str | None = None,
        profit_loss: float | None = None,
        r_multiple: float | None = None,
        mfe: float | None = None,
        mae: float | None = None,
        fill_price: float | None = None,
    ) -> DecisionRecord:
        record = self._record(symbol, decision, quote_spread)
        record.result = result
        record.rejection_reason = rejection_reason
        record.profit_loss = profit_loss
        record.r_multiple = r_multiple
        record.mae = mae
        record.mfe = mfe
        record.fill_price = fill_price
        self._append(record)
        return record

    def _record(self, symbol: str, decision: Decision, quote_spread: float) -> DecisionRecord:
        signal = decision.signal
        score = decision.score
        return DecisionRecord(
            time=datetime.now(timezone.utc),
            symbol=symbol,
            action=decision.action,
            reason=decision.reason,
            direction=signal.direction.value if signal else None,
            h1_trend=signal.h1_trend.value if signal else None,
            m30_trend=signal.m30_trend.value if signal else None,
            m15_trend=signal.m15_trend.value if signal else None,
            bos=bool(score and score.features.get("m15_bos")),
            mss=bool(score and score.features.get("m15_mss")),
            choch=bool(score and score.features.get("m15_choch")),
            liquidity_sweep=bool(score and score.features.get("sweep")),
            equal_liquidity=bool(score and score.features.get("sweep_equal")),
            order_block=bool(score and score.features.get("ob_interact")),
            fvg=bool(score and score.features.get("fvg_interact")),
            atr=float(score.features.get("atr_ratio", 0.0)) if score else 0.0,
            spread=quote_spread,
            session=("LONDON_NY" if score and score.features.get("session_london_ny") else "OTHER"),
            ml_probability=score.ml_probability if score else None,
            ml_buy_probability=score.ml_buy_probability if score else None,
            ml_sell_probability=score.ml_sell_probability if score else None,
            explanation=list(score.explanation) if score else [],
            features=dict(score.features) if score else {},
            summary=_summary(decision, score),
            rule_score=score.rule_score if score else None,
            final_score=score.total if score else None,
            grade=score.grade.value if score else None,
            entry=signal.plan.entry if signal else None,
            sl=signal.plan.sl if signal else None,
            tp=signal.plan.tp if signal else None,
            lots=signal.plan.lots if signal else None,
            signal_id=signal.signal_id if signal else None,
            rejection_reason=None if decision.signal else decision.reason,
        )

    def _append(self, record: DecisionRecord) -> None:
        with self.file.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
        if record.summary:
            with (self.path / "decisions.log").open("a", encoding="utf-8") as handle:
                handle.write(f"{record.time.isoformat()} {record.summary}\n")


def _flag(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def _prob(value: float | None) -> str:
    return "NA" if value is None else f"{value:.2f}"


def _summary(decision, score) -> str:
    if score is None:
        return f"Decision={decision.action.upper()} | Reason={decision.reason}"
    feats = score.features
    m15 = "MSS" if feats.get("m15_mss") else "BOS" if feats.get("m15_bos") else "CHOCH" if feats.get("m15_choch") else "NONE"
    side = (decision.signal.direction.value if decision.signal else "NONE")
    return (
        f"H1={decision.signal.h1_trend.value if decision.signal else 'NA'} | "
        f"M30={decision.signal.m30_trend.value if decision.signal else 'NA'} | "
        f"M15={m15}_{side} | "
        f"Sweep={_flag(bool(feats.get('sweep')))} | "
        f"OB={_flag(bool(feats.get('ob_interact')))} | "
        f"FVG={_flag(bool(feats.get('fvg_interact')))} | "
        f"ML_BUY={_prob(score.ml_buy_probability)} | "
        f"ML_SELL={_prob(score.ml_sell_probability)} | "
        f"Decision={decision.action.upper()} | "
        f"Reason={decision.reason}"
    )
