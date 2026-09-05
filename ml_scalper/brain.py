"""Python ML scalper brain.

Pipeline per cycle:

    MT5 data → M15 regime + M5 setup + optional M1 precision
             → technical filters (trend / pullback / EMA-VWAP / momentum)
             → dual ML heads (direction + expected TP-before-SL)
             → risk manager → command.json → MQL5 bridge

Python never places orders. The EA never invents BUY/SELL.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from . import indicators as ind
from .command_manager import CommandManager
from .config import Config
from .features import abnormal_conditions, build_live_features, live_setup_flags
from .logging_utils import format_decision_line, format_explanation, format_regime_report, setup_logger
from .ml_model import ScalperModels, TradeScore
from .mt5_connector import SyntheticConnector, make_connector
from .risk_manager import RiskManager


@dataclass
class Decision:
    action: str
    reason: str
    score: TradeScore | None = None


class ScalperBrain:
    def __init__(self, cfg: Config, connector=None, apply_recommended: bool = True):
        self.cfg = cfg
        cfg.ensure_dirs()
        self.log = setup_logger(cfg)
        self.model = ScalperModels.load(cfg.model_path)
        if apply_recommended:
            rec_c = self.model.metadata.get("recommended_ml_min_confidence")
            rec_o = self.model.metadata.get("recommended_min_outcome_prob")
            if rec_c is not None:
                cfg.ml_min_confidence = float(rec_c)
            if rec_o is not None:
                cfg.min_outcome_prob = float(rec_o)
        self.connector = connector or make_connector(cfg)
        self.commands = CommandManager(cfg)
        self.risk = RiskManager(cfg)
        self.log.info(
            "Loaded %s  dir=%s outcome=%s  P(dir)≥%.2f  P(TP)≥%.2f",
            cfg.symbol,
            self.model.direction.backend,
            self.model.outcome.backend,
            cfg.ml_min_confidence,
            cfg.min_outcome_prob,
        )

    def decide(self, flags: dict, score: TradeScore) -> Decision:
        thr = self.cfg.ml_min_confidence
        out_thr = self.cfg.min_outcome_prob
        buy_ml = score.p_buy >= thr and score.p_tp_buy >= out_thr
        sell_ml = score.p_sell >= thr and score.p_tp_sell >= out_thr
        buy_ok = bool(flags.get("buy_setup")) and buy_ml
        sell_ok = bool(flags.get("sell_setup")) and sell_ml

        if buy_ok and (not sell_ok or score.p_buy >= score.p_sell):
            return Decision("BUY", "filters + ML agree", score)
        if sell_ok:
            return Decision("SELL", "filters + ML agree", score)

        if not (flags.get("m15_bull") or flags.get("m15_bear")):
            reason = "no M15 trend regime"
        elif not (flags.get("buy_setup") or flags.get("sell_setup")):
            reason = "no M5 pullback/momentum setup"
        elif not buy_ml and not sell_ml:
            reason = (
                f"ML below gates (BUY {score.p_buy:.2f}/{score.p_tp_buy:.2f} "
                f"SELL {score.p_sell:.2f}/{score.p_tp_sell:.2f} "
                f"< {thr:.2f}/{out_thr:.2f})"
            )
        else:
            reason = "filters and ML did not agree"
        return Decision("NONE", reason, score)

    def _bars(self):
        cfg = self.cfg
        m15 = self.connector.get_rates(cfg.regime_timeframe, cfg.live_bars)
        m5 = self.connector.get_rates(cfg.setup_timeframe, cfg.live_bars)
        m1 = None
        if cfg.use_m1_precision:
            m1 = self.connector.get_rates(cfg.entry_timeframe, cfg.live_bars)
        return m15, m5, m1

    def run_cycle(self) -> Decision:
        cfg = self.cfg
        self.commands.touch_heartbeat()
        status = self.commands.read_status()
        open_positions = self.commands.open_positions(status)

        m15, m5, m1 = self._bars()
        last, buy_feat, sell_feat = build_live_features(m15, m5, m1, cfg)
        row = last.iloc[0]
        flags = live_setup_flags(row, cfg)
        score = self.model.predict(last, buy_feat, sell_feat)
        decision = self.decide(flags, score)

        m15_tag = "BULLISH" if flags["m15_bull"] else ("BEARISH" if flags["m15_bear"] else "FLAT")
        m5_tag = "BUY_SETUP" if flags["buy_setup"] else ("SELL_SETUP" if flags["sell_setup"] else "NONE")
        self.log.info(
            format_decision_line(
                cfg.symbol, m15_tag, m5_tag,
                score.p_buy, score.p_sell, score.p_none,
                score.p_tp_buy, score.p_tp_sell, decision.action,
            )
        )

        if decision.action == "NONE":
            self.log.info("No trade: %s", decision.reason)
            return decision

        tick = self.connector.get_tick(cfg.symbol)
        account = self.connector.account_info()
        balance = float(account.get("balance", 0.0) or 0.0)
        self.risk.sync_from_status(status, balance)

        block = self.risk.protection_block(balance)
        if block:
            self.log.info("Skip %s: %s", decision.action, block)
            return Decision("NONE", block, score)

        if not self.risk.can_open(open_positions):
            self.log.info("Skip %s: existing open position (%d)", decision.action, open_positions)
            return Decision("NONE", "existing position", score)

        abnormal = abnormal_conditions(row, tick["spread_points"], cfg)
        if abnormal:
            self.log.warning("Skip %s: %s", decision.action, abnormal)
            return Decision("NONE", abnormal, score)

        if not self.risk.check_spread(tick["spread_points"]):
            self.log.warning("Skip %s: spread %.1f", decision.action, tick["spread_points"])
            return Decision("NONE", "spread too wide", score)

        if account.get("trade_allowed") is False:
            return Decision("NONE", "account trading not allowed", score)

        symbol_info = self.connector.symbol_info(cfg.symbol)
        atr_now = float(ind.atr(m5, cfg.atr_period).iloc[-1])
        if not np_finite(atr_now) or atr_now <= 0:
            return Decision("NONE", "invalid ATR", score)

        entry = tick["ask"] if decision.action == "BUY" else tick["bid"]
        plan = self.risk.build_trade_plan(decision.action, entry, atr_now, symbol_info, balance)

        problems = []
        if plan.lots <= 0:
            problems.append("lots<=0")
        if not self.risk.validate_rr(decision.action, plan.entry, plan.sl, plan.tp):
            problems.append(f"rr<{cfg.risk_reward:g} (got {plan.rr:.2f})")
        if decision.action == "BUY" and not (plan.sl < plan.entry < plan.tp):
            problems.append("invalid BUY sl/tp ordering")
        if decision.action == "SELL" and not (plan.tp < plan.entry < plan.sl):
            problems.append("invalid SELL sl/tp ordering")
        free_margin = float(account.get("margin_free", 0.0) or 0.0)
        if not self.risk.margin_ok(plan.lots, plan.entry, symbol_info, free_margin):
            problems.append("insufficient free margin")
        if problems:
            self.log.warning("Skip %s: %s", decision.action, "; ".join(problems))
            return Decision("NONE", "; ".join(problems), score)

        if not self.commands.should_send(decision.action, plan.entry, plan.sl):
            self.log.info("Skip %s: duplicate setup within cooldown", decision.action)
            return Decision("NONE", "duplicate/cooldown", score)

        extra = {
            "p_buy": round(score.p_buy, 4),
            "p_sell": round(score.p_sell, 4),
            "p_none": round(score.p_none, 4),
            "p_tp": round(score.p_tp_buy if decision.action == "BUY" else score.p_tp_sell, 4),
            "atr": round(plan.atr, 6),
        }
        cmd = self.commands.write_trade_command(
            action=decision.action,
            lots=plan.lots,
            sl=plan.sl,
            tp=plan.tp,
            entry=plan.entry,
            breakeven_r=plan.breakeven_r,
            trail_start_r=plan.trail_start_r,
            trail_enabled=plan.trail_enabled,
            extra=extra,
        )
        self.commands.mark_sent(decision.action, plan.entry, plan.sl)
        chosen = buy_feat if decision.action == "BUY" else sell_feat
        self.log.info(
            "COMMAND %s id=%s lots=%s entry=%s sl=%s tp=%s rr=%.2f P(dir)=%.2f P(TP)=%.2f",
            decision.action,
            cmd["id"],
            plan.lots,
            plan.entry,
            plan.sl,
            plan.tp,
            plan.rr,
            score.p_buy if decision.action == "BUY" else score.p_sell,
            extra["p_tp"],
        )
        self.log.info(format_explanation(self.model.outcome.explain(chosen)))
        return decision

    def analyze_report(self) -> str:
        m15, m5, m1 = self._bars()
        last, buy_feat, sell_feat = build_live_features(m15, m5, m1, self.cfg)
        flags = live_setup_flags(last.iloc[0], self.cfg)
        score = self.model.predict(last, buy_feat, sell_feat)
        tick = self.connector.get_tick(self.cfg.symbol)
        decision = self.decide(flags, score)
        report = format_regime_report(self.cfg.symbol, flags, tick, score)
        report += f"\nDECISION={decision.action}" + ("" if decision.action != "NONE" else f"  ({decision.reason})")
        for line in report.splitlines():
            self.log.info(line)
        return report

    def run_live(self, iterations: int | None = None) -> None:
        i = 0
        while iterations is None or i < iterations:
            try:
                self.run_cycle()
            except Exception as exc:
                self.log.exception("Cycle error: %s", exc)
            i += 1
            if iterations is None or i < iterations:
                time.sleep(self.cfg.poll_interval_sec)

    def run_replay(self, steps: int, warmup: int = 250, start_index: int | None = None) -> dict:
        if not isinstance(self.connector, SyntheticConnector):
            raise RuntimeError("replay mode requires the synthetic connector")
        timeline = self.connector.timeline()
        if start_index is not None:
            start = max(warmup, start_index)
            window = timeline[start : start + steps]
        else:
            start = max(warmup, len(timeline) - steps)
            window = timeline[start:]
        counts = {"BUY": 0, "SELL": 0, "NONE": 0}
        for ts in window:
            self.connector.set_cutoff_time(ts)
            decision = self.run_cycle()
            counts[decision.action] = counts.get(decision.action, 0) + 1
        self.log.info("Replay finished over %d bars: %s", len(window), counts)
        return counts


def np_finite(value: float) -> bool:
    return value == value and abs(value) != float("inf")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ml_scalper", description="ML trend/pullback scalper brain.")
    p.add_argument("--source", choices=["mt5", "synthetic", "csv"], default="mt5")
    p.add_argument("--symbol", default="Volatility 75 Index")
    p.add_argument("--once", action="store_true")
    p.add_argument("--analyze", action="store_true")
    p.add_argument("--iterations", type=int, default=None)
    p.add_argument("--replay", type=int, default=None)
    p.add_argument("--replay-start", type=int, default=None)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--balance", type=float, default=1000.0)
    p.add_argument("--min-confidence", type=float, default=None, help="Override P(direction) gate.")
    p.add_argument("--min-outcome", type=float, default=None, help="Override P(TP before SL) gate.")
    p.add_argument("--bridge-dir", type=str, default=None)
    p.add_argument("--no-recommended-thresholds", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.from_env(data_source=args.source, symbol=args.symbol)
    if args.min_confidence is not None:
        cfg.ml_min_confidence = args.min_confidence
    if args.min_outcome is not None:
        cfg.min_outcome_prob = args.min_outcome
    if args.bridge_dir:
        from pathlib import Path

        cfg.bridge_dir = Path(args.bridge_dir)
    cfg.ensure_dirs()

    connector = None
    if cfg.data_source == "synthetic":
        connector = SyntheticConnector(cfg, seed=args.seed, balance=args.balance)

    apply_rec = not args.no_recommended_thresholds and args.min_confidence is None
    brain = ScalperBrain(cfg, connector=connector, apply_recommended=apply_rec)
    if args.min_confidence is not None:
        cfg.ml_min_confidence = args.min_confidence
    if args.min_outcome is not None:
        cfg.min_outcome_prob = args.min_outcome

    if args.analyze:
        print(brain.analyze_report())
    elif args.replay is not None:
        brain.run_replay(args.replay, start_index=args.replay_start)
    elif args.once:
        brain.run_cycle()
    else:
        brain.run_live(iterations=args.iterations)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
