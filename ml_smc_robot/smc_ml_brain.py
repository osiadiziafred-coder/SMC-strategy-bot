"""The Python ML/SMC brain.

Pipeline per cycle:

    MT5 data -> SMC detection (H1 bias / M30 confirm / M15 entry)
             -> feature engineering -> trained ML model -> BUY/SELL probability
             -> SMC validation + risk management -> command.json -> MQL5 bridge

The brain only ever *proposes* trades by writing ``command.json``; the MQL5 EA
performs broker-side validation and execution. The brain also sends a regular
heartbeat so the EA can refuse new entries if Python goes silent.

Modes:

* live (default): loop forever polling MT5.
* ``--once``: run a single decision cycle (dry-run friendly).
* ``--replay N``: step the offline synthetic feed forward N bars, running the
  full pipeline each bar. Useful to demonstrate the end-to-end flow without a
  terminal.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from .config import Config
from .command_manager import CommandManager
from .features import build_live_features
from .logging_utils import format_decision_line, format_explanation, format_smc_report, setup_logger
from .ml_model import MLModel
from .mt5_connector import SyntheticConnector, make_connector
from .risk_manager import RiskManager
from . import smc_detector as smc


@dataclass
class Decision:
    action: str  # BUY | SELL | NONE
    reason: str
    buy_prob: float
    sell_prob: float
    features = None


class SMCBrain:
    def __init__(self, cfg: Config, connector=None):
        self.cfg = cfg
        cfg.ensure_dirs()
        self.log = setup_logger(cfg)
        self.model = MLModel.load(cfg.model_path)
        self.connector = connector or make_connector(cfg)
        self.commands = CommandManager(cfg)
        self.risk = RiskManager(cfg)
        self.log.info(
            "Loaded model backend=%s features=%d min_conf=%.2f",
            self.model.backend, len(self.model.feature_names), cfg.ml_min_confidence,
        )
        top = list(self.model.feature_importance().items())[:6]
        self.log.info("Global feature importance: %s", ", ".join(f"{k}={v:.3f}" for k, v in top))

    # -- decision logic ----------------------------------------------------
    def decide(self, h1: smc.SMCState, m30: smc.SMCState, m15: smc.SMCState,
               buy_prob: float, sell_prob: float) -> Decision:
        thr = self.cfg.ml_min_confidence

        # H1 provides directional bias; M30 must not oppose it.
        bull_context = h1.bias == smc.Bias.BULLISH and m30.trend >= 0
        bear_context = h1.bias == smc.Bias.BEARISH and m30.trend <= 0

        # M15 must show structure supporting the direction. A standing trend is
        # itself a sequence of bullish/bearish BOS, so trend alignment counts as
        # structural confirmation for retracement entries (in addition to a fresh
        # BOS/CHoCH/MSS print on the current bar).
        bull_struct = (m15.bos > 0 or m15.choch > 0 or m15.mss > 0 or m15.trend > 0)
        bear_struct = (m15.bos < 0 or m15.choch < 0 or m15.mss < 0 or m15.trend < 0)

        # A valid entry area (order block or fair value gap) must exist.
        bull_area = m15.nearest_bull_ob is not None or m15.nearest_bull_fvg is not None
        bear_area = m15.nearest_bear_ob is not None or m15.nearest_bear_fvg is not None

        # Premium/discount: avoid buying at the extreme top / selling at the
        # extreme bottom. The ML model already weighs location via its ``pd_dir``
        # feature, so this is a light guard rather than a hard discount-only rule.
        bull_location = m15.premium_discount <= 0.85
        bear_location = m15.premium_discount >= 0.15

        buy_ok = bull_context and bull_struct and bull_area and bull_location and buy_prob >= thr
        sell_ok = bear_context and bear_struct and bear_area and bear_location and sell_prob >= thr

        if buy_ok and (not sell_ok or buy_prob >= sell_prob):
            return Decision("BUY", "all conditions met", buy_prob, sell_prob)
        if sell_ok:
            return Decision("SELL", "all conditions met", buy_prob, sell_prob)

        # Build a concise rejection reason.
        if not (bull_context or bear_context):
            reason = "no H1/M30 directional context"
        elif buy_prob < thr and sell_prob < thr:
            reason = f"ML below threshold (buy={buy_prob:.2f}, sell={sell_prob:.2f} < {thr:.2f})"
        elif not (bull_struct or bear_struct):
            reason = "no M15 structure (BOS/MSS/CHoCH)"
        elif not (bull_area or bear_area):
            reason = "no OB/FVG entry area"
        else:
            reason = "SMC/ML conditions not aligned"
        return Decision("NONE", reason, buy_prob, sell_prob)

    # -- single cycle ------------------------------------------------------
    def run_cycle(self) -> Decision:
        cfg = self.cfg
        self.commands.touch_heartbeat()

        status = self.commands.read_status()
        open_positions = self.commands.open_positions(status)

        h1_df = self.connector.get_rates(cfg.bias_timeframe, cfg.live_bars)
        m30_df = self.connector.get_rates(cfg.confirm_timeframe, cfg.live_bars)
        m15_df = self.connector.get_rates(cfg.entry_timeframe, cfg.live_bars)

        h1 = smc.analyze(h1_df, cfg.atr_period)
        m30 = smc.analyze(m30_df, cfg.atr_period)
        m15 = smc.analyze(m15_df, cfg.atr_period)

        _, buy_feat, sell_feat = build_live_features(h1_df, m30_df, m15_df, cfg)
        buy_prob = float(self.model.predict_success_proba(buy_feat)[0])
        sell_prob = float(self.model.predict_success_proba(sell_feat)[0])

        decision = self.decide(h1, m30, m15, buy_prob, sell_prob)

        m15_setup = self._setup_tag(m15)
        ob_present = bool(m15.nearest_bull_ob or m15.nearest_bear_ob)
        fvg_present = bool(m15.nearest_bull_fvg or m15.nearest_bear_fvg)
        self.log.info(
            format_decision_line(
                cfg.symbol, h1.bias.value, m30.bias.value, m15_setup,
                m15.bos, m15.mss, m15.choch, m15.liquidity_sweep, m15.equal_liquidity_sweep,
                ob_present, fvg_present, buy_prob, sell_prob, decision.action,
            )
        )

        if decision.action == "NONE":
            self.log.info("No trade: %s", decision.reason)
            return decision

        # --- Safety checks before emitting a command ----------------------
        if not self.risk.can_open(open_positions):
            self.log.info("Skip %s: existing open position (%d)", decision.action, open_positions)
            return Decision("NONE", "existing position", buy_prob, sell_prob)

        tick = self.connector.get_tick(cfg.symbol)
        if not self.risk.check_spread(tick["spread_points"]):
            self.log.warning("Skip %s: spread %.1f > max %.1f", decision.action,
                             tick["spread_points"], cfg.max_spread_points)
            return Decision("NONE", "spread too wide", buy_prob, sell_prob)

        symbol_info = self.connector.symbol_info(cfg.symbol)
        balance = self.connector.account_info().get("balance", 0.0)
        entry = tick["ask"] if decision.action == "BUY" else tick["bid"]
        state = m15
        plan = self.risk.build_trade_plan(decision.action, entry, state, symbol_info, balance)

        problems = []
        if plan.lots <= 0:
            problems.append("lots<=0")
        if not self.risk.validate_rr(decision.action, plan.entry, plan.sl, plan.tp):
            problems.append(f"rr!=1:{cfg.risk_reward:g} (got {plan.rr:.2f})")
        if decision.action == "BUY" and not (plan.sl < plan.entry < plan.tp):
            problems.append("invalid BUY sl/tp ordering")
        if decision.action == "SELL" and not (plan.tp < plan.entry < plan.sl):
            problems.append("invalid SELL sl/tp ordering")
        if problems:
            self.log.warning("Skip %s: %s", decision.action, "; ".join(problems))
            return Decision("NONE", "; ".join(problems), buy_prob, sell_prob)

        if not self.commands.should_send(decision.action, plan.entry, plan.sl):
            self.log.info("Skip %s: duplicate setup within cooldown", decision.action)
            return Decision("NONE", "duplicate/cooldown", buy_prob, sell_prob)

        cmd = self.commands.write_trade_command(
            action=decision.action, lots=plan.lots, sl=plan.sl, tp=plan.tp, entry=plan.entry,
            breakeven_r=plan.breakeven_r, trail_start_r=plan.trail_start_r,
            trail_enabled=plan.trail_enabled,
        )
        self.commands.mark_sent(decision.action, plan.entry, plan.sl)

        chosen_feat = buy_feat if decision.action == "BUY" else sell_feat
        explain = self.model.explain(chosen_feat)
        prob = buy_prob if decision.action == "BUY" else sell_prob
        self.log.info(
            "COMMAND %s id=%s lots=%.2f entry=%.3f sl=%.3f tp=%.3f rr=%.2f prob=%.2f",
            decision.action, cmd["id"], plan.lots, plan.entry, plan.sl, plan.tp, plan.rr, prob,
        )
        self.log.info(format_explanation(explain))
        return decision

    @staticmethod
    def _setup_tag(m15: smc.SMCState) -> str:
        if m15.mss > 0:
            return "MSS_BULLISH"
        if m15.mss < 0:
            return "MSS_BEARISH"
        if m15.choch > 0:
            return "CHOCH_BULLISH"
        if m15.choch < 0:
            return "CHOCH_BEARISH"
        if m15.bos > 0:
            return "BOS_BULLISH"
        if m15.bos < 0:
            return "BOS_BEARISH"
        return "NONE"

    # -- SMC readout -------------------------------------------------------
    def analyze_report(self) -> str:
        """Build a full multi-timeframe SMC readout and log it.

        Brings out Liquidity sweep, Equal-liquidity sweep, Order Block, FVG,
        BOS, CHoCH and MSS across H1/M30/M15 plus the ML probabilities.
        """

        cfg = self.cfg
        h1_df = self.connector.get_rates(cfg.bias_timeframe, cfg.live_bars)
        m30_df = self.connector.get_rates(cfg.confirm_timeframe, cfg.live_bars)
        m15_df = self.connector.get_rates(cfg.entry_timeframe, cfg.live_bars)

        states = {
            "H1": smc.analyze(h1_df, cfg.atr_period),
            "M30": smc.analyze(m30_df, cfg.atr_period),
            "M15": smc.analyze(m15_df, cfg.atr_period),
        }
        tick = self.connector.get_tick(cfg.symbol)

        _, buy_feat, sell_feat = build_live_features(h1_df, m30_df, m15_df, cfg)
        buy_prob = float(self.model.predict_success_proba(buy_feat)[0])
        sell_prob = float(self.model.predict_success_proba(sell_feat)[0])
        decision = self.decide(states["H1"], states["M30"], states["M15"], buy_prob, sell_prob)

        report = format_smc_report(cfg.symbol, states, tick)
        report += (
            f"\nML_BUY={buy_prob:.2f}  ML_SELL={sell_prob:.2f}  "
            f"MIN_CONF={cfg.ml_min_confidence:.2f}  ->  DECISION={decision.action}"
            + ("" if decision.action != "NONE" else f"  ({decision.reason})")
        )
        for line in report.splitlines():
            self.log.info(line)
        return report

    # -- loop drivers ------------------------------------------------------
    def run_live(self, iterations: int | None = None) -> None:
        i = 0
        while iterations is None or i < iterations:
            try:
                self.run_cycle()
            except Exception as exc:  # keep the loop alive; log and continue
                self.log.exception("Cycle error: %s", exc)
            i += 1
            if iterations is None or i < iterations:
                time.sleep(self.cfg.poll_interval_sec)

    def run_replay(self, steps: int, warmup: int = 300, start_index: int | None = None) -> dict:
        """Replay the offline synthetic feed to demonstrate the full pipeline."""

        if not isinstance(self.connector, SyntheticConnector):
            raise RuntimeError("replay mode requires the synthetic connector")
        timeline = self.connector.timeline()
        if start_index is not None:
            start = max(warmup, start_index)
            window = timeline[start:start + steps]
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="smc_ml_brain", description="Python ML/SMC trading brain.")
    p.add_argument("--source", choices=["mt5", "synthetic", "csv"], default="mt5")
    p.add_argument("--once", action="store_true", help="Run a single decision cycle then exit.")
    p.add_argument("--analyze", action="store_true",
                   help="Print a full multi-timeframe SMC readout then exit.")
    p.add_argument("--iterations", type=int, default=None, help="Number of live cycles then exit.")
    p.add_argument("--replay", type=int, default=None, help="Replay N synthetic bars (offline demo).")
    p.add_argument("--replay-start", type=int, default=None, help="Start index for replay window.")
    p.add_argument("--seed", type=int, default=7, help="Synthetic data seed.")
    p.add_argument("--balance", type=float, default=1000.0, help="Synthetic account balance.")
    p.add_argument("--min-confidence", type=float, default=None, help="Override ML_MIN_CONFIDENCE.")
    p.add_argument("--bridge-dir", type=str, default=None, help="Override bridge directory.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.from_env(data_source=args.source)
    if args.min_confidence is not None:
        cfg.ml_min_confidence = args.min_confidence
    if args.bridge_dir:
        from pathlib import Path

        cfg.bridge_dir = Path(args.bridge_dir)
    cfg.ensure_dirs()

    connector = None
    if cfg.data_source == "synthetic":
        connector = SyntheticConnector(cfg, seed=args.seed, balance=args.balance)

    brain = SMCBrain(cfg, connector=connector)

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
