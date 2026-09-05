"""Risk management for the ML scalper.

Stops are ATR/volatility based (no structure/OB anchors). Take-profit enforces
a minimum 1:2 reward-to-risk. Position size is computed from account balance
and each instrument's lot step.

Protection (enforced here and again in the MQL5 EA):

* one open position
* move SL to breakeven at +1R
* maximum daily-loss halt
* maximum consecutive-loss halt
* skip abnormal spread / volatility
* margin sanity check
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import Config


@dataclass
class TradePlan:
    direction: str
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
    atr: float

    def as_log_dict(self) -> dict:
        return {
            "entry": self.entry,
            "sl": self.sl,
            "tp": self.tp,
            "lots": self.lots,
            "rr": round(self.rr, 2),
            "atr": round(self.atr, 5),
        }


@dataclass
class ProtectionState:
    day: str = ""
    starting_balance: float = 0.0
    realized_pnl: float = 0.0
    consecutive_losses: int = 0
    trades_today: int = 0
    halted: bool = False
    halt_reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class RiskManager:
    def __init__(self, cfg: Config, state: ProtectionState | None = None):
        self.cfg = cfg
        self.state = state or ProtectionState()

    def _lot_decimals(self, step: float) -> int:
        if step <= 0:
            return 2
        return max(0, int(round(-math.log10(step))))

    def normalize_lot(self, lot: float, symbol_info: dict) -> float:
        step = symbol_info.get("volume_step", self.cfg.lot_step) or self.cfg.lot_step
        vmin = symbol_info.get("volume_min", self.cfg.min_lot)
        vmax = symbol_info.get("volume_max", self.cfg.max_lot)
        steps = math.floor(lot / step + 1e-9)
        lot = steps * step
        lot = max(vmin, min(vmax, lot))
        return round(lot, self._lot_decimals(step))

    def lot_size(self, balance: float, symbol_info: dict) -> float:
        raw = (balance / self.cfg.lot_per_balance) * self.cfg.lot_unit
        return self.normalize_lot(raw, symbol_info)

    def compute_sl_tp(
        self, direction: str, entry: float, atr: float, symbol_info: dict
    ) -> tuple[float, float, float]:
        point = symbol_info.get("point", self.cfg.point) or self.cfg.point
        digits = int(symbol_info.get("digits", self.cfg.digits))
        atr = atr if atr and atr > 0 else entry * 0.001
        risk = max(atr * self.cfg.atr_sl_mult, self.cfg.min_sl_distance_points * point)
        if direction == "BUY":
            sl = entry - risk
            tp = entry + self.cfg.risk_reward * risk
        else:
            sl = entry + risk
            tp = entry - self.cfg.risk_reward * risk
        return round(sl, digits), round(tp, digits), abs(entry - sl)

    def validate_rr(self, direction: str, entry: float, sl: float, tp: float, tol: float = 0.25) -> bool:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk <= 0:
            return False
        return (reward / risk) + 1e-9 >= self.cfg.risk_reward - tol

    def check_spread(self, spread_points: float) -> bool:
        return spread_points <= self.cfg.max_spread_points

    def can_open(self, open_positions: int) -> bool:
        return open_positions < self.cfg.max_open_positions

    def estimated_margin(self, lots: float, price: float, symbol_info: dict) -> float:
        contract = float(symbol_info.get("trade_contract_size", 1.0) or 1.0)
        leverage = max(self.cfg.leverage, 1.0)
        return abs(lots) * contract * price / leverage

    def margin_ok(self, lots: float, price: float, symbol_info: dict, free_margin: float) -> bool:
        if free_margin <= 0:
            return True  # unknown — let the EA decide
        need = self.estimated_margin(lots, price, symbol_info)
        return need <= 0.5 * free_margin

    def sync_from_status(self, status: dict, balance: float) -> None:
        """Refresh daily / streak stats from the EA status payload when present."""

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.state.day != today:
            self.state = ProtectionState(day=today, starting_balance=balance)
        risk = status.get("risk") or {}
        if "daily_pnl" in risk:
            self.state.realized_pnl = float(risk["daily_pnl"])
        if "consecutive_losses" in risk:
            self.state.consecutive_losses = int(risk["consecutive_losses"])
        if "trades_today" in risk:
            self.state.trades_today = int(risk["trades_today"])
        if self.state.starting_balance <= 0:
            self.state.starting_balance = balance

    def record_closed_trade(self, pnl: float) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.state.day != today:
            self.state = ProtectionState(day=today, starting_balance=self.state.starting_balance)
        self.state.realized_pnl += pnl
        self.state.trades_today += 1
        if pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

    def protection_block(self, balance: float) -> str | None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.state.day != today:
            self.state = ProtectionState(day=today, starting_balance=balance)
        start = self.state.starting_balance or balance
        if start > 0:
            loss_pct = -self.state.realized_pnl / start * 100.0
            if self.state.realized_pnl < 0 and loss_pct >= self.cfg.max_daily_loss_pct:
                self.state.halted = True
                self.state.halt_reason = f"daily loss {loss_pct:.2f}% >= {self.cfg.max_daily_loss_pct:g}%"
                return self.state.halt_reason
        if self.state.consecutive_losses >= self.cfg.max_consecutive_losses:
            self.state.halted = True
            self.state.halt_reason = (
                f"consecutive losses {self.state.consecutive_losses} >= {self.cfg.max_consecutive_losses}"
            )
            return self.state.halt_reason
        if self.state.trades_today >= self.cfg.max_trades_per_day:
            return f"max trades per day ({self.cfg.max_trades_per_day}) reached"
        return None

    def build_trade_plan(
        self,
        direction: str,
        entry: float,
        atr: float,
        symbol_info: dict,
        balance: float,
    ) -> TradePlan:
        sl, tp, risk = self.compute_sl_tp(direction, entry, atr, symbol_info)
        lots = self.lot_size(balance, symbol_info)
        reward = abs(tp - entry)
        rr = reward / risk if risk > 0 else 0.0
        return TradePlan(
            direction=direction,
            entry=round(entry, int(symbol_info.get("digits", self.cfg.digits))),
            sl=sl,
            tp=tp,
            lots=lots,
            risk_distance=risk,
            reward_distance=reward,
            rr=rr,
            breakeven_r=self.cfg.breakeven_r,
            trail_start_r=self.cfg.trail_start_r,
            trail_enabled=self.cfg.trail_enabled,
            atr=float(atr),
        )

    def save_state(self, path: Path) -> None:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.state.as_dict(), indent=2), encoding="utf-8")

    def load_state(self, path: Path) -> None:
        import json

        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.state = ProtectionState(**{k: data[k] for k in ProtectionState().__dict__ if k in data})
