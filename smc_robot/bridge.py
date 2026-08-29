"""File-based Python ↔ MQL5 command/status protocol.

Python writes command.json. The MQL5 EA validates, executes, and writes status.json.
The EA does not invent its own entries.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smc_robot.config import Settings
from smc_robot.models import Direction, Signal


class FileBridge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.directory = Path(settings.bridge.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.command_path = self.directory / settings.bridge.command_file
        self.status_path = self.directory / settings.bridge.status_file
        self._last_sent = ""

    def heartbeat(self) -> None:
        self._write_command(
            {
                "action": "HEARTBEAT",
                "id": f"hb-{int(time.time())}",
                "symbol": self.settings.symbol,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )

    def send_signal(self, signal: Signal) -> str:
        command = {
            "action": signal.direction.value,
            "id": signal.signal_id,
            "symbol": self.settings.symbol,
            "lots": signal.plan.lots,
            "sl": signal.plan.sl,
            "tp": signal.plan.tp,
            "magic": self.settings.risk.magic,
            "deviation": int(self.settings.protection.max_slippage_points),
            "ml_probability": signal.score.ml_probability,
            "grade": signal.grade.value,
            "comment": (self.settings.risk.comment + "-" + signal.signal_id)[:31],
            "manage": {
                "breakeven_r": self.settings.risk.breakeven_r,
                "trail_start_r": self.settings.risk.trail_start_r,
                "trail_enabled": self.settings.risk.trail_enabled,
            },
            "time": datetime.now(timezone.utc).isoformat(),
        }
        self._write_command(command)
        self._last_sent = signal.signal_id
        return signal.signal_id

    def send_modify(self, ticket: int, sl: float, tp: float, signal_id: str) -> None:
        self._write_command(
            {
                "action": "MODIFY",
                "id": f"{signal_id}-mod-{int(time.time())}",
                "symbol": self.settings.symbol,
                "ticket": ticket,
                "sl": sl,
                "tp": tp,
                "magic": self.settings.risk.magic,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )

    def read_status(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {}
        try:
            return json.loads(self.status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def last_result_for(self, signal_id: str) -> dict[str, Any] | None:
        status = self.read_status()
        result = status.get("last_result") or {}
        if result.get("id") == signal_id:
            return result
        return None

    def connected(self) -> bool:
        status = self.read_status()
        if not status:
            return False
        raw = status.get("time")
        if not raw:
            return False
        try:
            stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return False
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        return age <= self.settings.bridge.heartbeat_seconds * 3

    def _write_command(self, payload: dict[str, Any]) -> None:
        tmp = self.command_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.command_path)


def command_from_signal(signal: Signal, settings: Settings) -> dict[str, Any]:
    bridge = FileBridge(settings)
    return {
        "action": signal.direction.value,
        "id": signal.signal_id,
        "symbol": settings.symbol,
        "lots": signal.plan.lots,
        "sl": signal.plan.sl,
        "tp": signal.plan.tp,
        "direction": signal.direction.value,
    }
