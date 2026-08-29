from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from smc_robot.config import Settings


@dataclass
class DailyGuard:
    settings: Settings
    day: date | None = None
    start_equity: float = 0.0
    realized_pnl: float = 0.0
    trades: int = 0
    consecutive_losses: int = 0
    last_close_bar_index: int | None = None
    last_was_loss: bool = False
    seen_tickets: set[int] = field(default_factory=set)

    def roll(self, now: datetime, equity: float) -> None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        today = now.date()
        if self.day != today:
            self.day = today
            self.start_equity = equity
            self.realized_pnl = 0.0
            self.trades = 0
            self.consecutive_losses = 0

    def allow(self, equity: float) -> tuple[bool, str]:
        cfg = self.settings.daily_risk
        base = self.start_equity or equity
        if cfg.max_trades_per_day > 0 and self.trades >= cfg.max_trades_per_day:
            return False, "max_daily_trades"
        if cfg.max_consecutive_losses > 0 and self.consecutive_losses >= cfg.max_consecutive_losses:
            return False, "max_consecutive_losses"
        if cfg.max_daily_loss_percent > 0 and base > 0:
            if self.realized_pnl <= -abs(base * cfg.max_daily_loss_percent / 100.0):
                return False, "max_daily_loss"
        if cfg.max_daily_profit_percent > 0 and base > 0:
            if self.realized_pnl >= abs(base * cfg.max_daily_profit_percent / 100.0):
                return False, "max_daily_profit"
        return True, "ok"

    def cooldown_active(self, current_bar_index: int) -> tuple[bool, str]:
        if self.last_close_bar_index is None:
            return False, ""
        wait = self.settings.cooldown.bars_after_loss if self.last_was_loss else self.settings.cooldown.bars_after_close
        if current_bar_index - self.last_close_bar_index < wait:
            return True, "cooldown_active"
        return False, ""

    def record_close(self, pnl: float, bar_index: int) -> None:
        self.realized_pnl += pnl
        self.trades += 1
        self.last_close_bar_index = bar_index
        self.last_was_loss = pnl < 0
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
