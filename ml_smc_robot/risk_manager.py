"""Risk management: position sizing, SL/TP derivation and trade validation.

Stops and targets are anchored to the actual SMC setup (order block / swing
levels) with an ATR floor, and the take-profit enforces the configured 1:2
risk-reward. Lot size follows the ``balance / 100 * 0.01`` rule, normalised to the
broker's volume step/min/max.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import Config
from .smc_detector import SMCState


@dataclass
class TradePlan:
    direction: str          # "BUY" | "SELL"
    entry: float
    sl: float
    tp: float
    lots: float
    risk_distance: float
    reward_distance: float
    rr: float
    breakeven_r: float
    trail_start_r: float
    trail_enabled: bool

    def as_log_dict(self) -> dict:
        return {
            "entry": self.entry,
            "sl": self.sl,
            "tp": self.tp,
            "lots": self.lots,
            "rr": round(self.rr, 2),
        }


class RiskManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    # -- position sizing ---------------------------------------------------
    def normalize_lot(self, lot: float, symbol_info: dict) -> float:
        step = symbol_info.get("volume_step", self.cfg.lot_step) or self.cfg.lot_step
        vmin = symbol_info.get("volume_min", self.cfg.min_lot)
        vmax = symbol_info.get("volume_max", self.cfg.max_lot)
        steps = math.floor(lot / step + 1e-9)
        lot = steps * step
        lot = max(vmin, min(vmax, lot))
        # Round to the step's decimal precision to avoid float noise.
        decimals = max(0, int(round(-math.log10(step)))) if step > 0 else 2
        return round(lot, decimals)

    def lot_size(self, balance: float, symbol_info: dict) -> float:
        raw = (balance / self.cfg.lot_per_balance) * self.cfg.lot_unit
        return self.normalize_lot(raw, symbol_info)

    # -- stop loss / take profit ------------------------------------------
    def compute_sl_tp(self, direction: str, entry: float, state: SMCState, symbol_info: dict) -> tuple[float, float, float]:
        point = symbol_info.get("point", self.cfg.point) or self.cfg.point
        digits = symbol_info.get("digits", 2)
        buffer = self.cfg.breakeven_buffer_points * point

        atr = state.atr if state.atr and state.atr > 0 else entry * 0.001
        atr_risk = max(atr * self.cfg.atr_sl_mult, self.cfg.min_sl_distance_points * point)

        if direction == "BUY":
            anchors = [a for a in (state.swing_low, getattr(state.nearest_bull_ob, "bottom", None)) if a]
            structural_sl = (min(anchors) - buffer) if anchors else (entry - atr_risk)
            risk = entry - structural_sl
            if risk <= 0 or risk > 3 * atr_risk:
                risk = atr_risk
            sl = entry - risk
            tp = entry + self.cfg.risk_reward * risk
        else:  # SELL
            anchors = [a for a in (state.swing_high, getattr(state.nearest_bear_ob, "top", None)) if a]
            structural_sl = (max(anchors) + buffer) if anchors else (entry + atr_risk)
            risk = structural_sl - entry
            if risk <= 0 or risk > 3 * atr_risk:
                risk = atr_risk
            sl = entry + risk
            tp = entry - self.cfg.risk_reward * risk

        return round(sl, digits), round(tp, digits), abs(entry - sl)

    def validate_rr(self, direction: str, entry: float, sl: float, tp: float, tol: float = 0.25) -> bool:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk <= 0:
            return False
        rr = reward / risk
        return abs(rr - self.cfg.risk_reward) <= tol

    # -- gating helpers ----------------------------------------------------
    def check_spread(self, spread_points: float) -> bool:
        return spread_points <= self.cfg.max_spread_points

    def can_open(self, open_positions: int) -> bool:
        return open_positions < self.cfg.max_open_positions

    def build_trade_plan(self, direction: str, entry: float, state: SMCState, symbol_info: dict, balance: float) -> TradePlan:
        sl, tp, risk = self.compute_sl_tp(direction, entry, state, symbol_info)
        lots = self.lot_size(balance, symbol_info)
        reward = abs(tp - entry)
        rr = reward / risk if risk > 0 else 0.0
        return TradePlan(
            direction=direction,
            entry=round(entry, symbol_info.get("digits", 2)),
            sl=sl,
            tp=tp,
            lots=lots,
            risk_distance=risk,
            reward_distance=reward,
            rr=rr,
            breakeven_r=self.cfg.breakeven_r,
            trail_start_r=self.cfg.trail_start_r,
            trail_enabled=self.cfg.trail_enabled,
        )
