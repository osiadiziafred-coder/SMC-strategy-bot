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
from smc_robot.models import Signal


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
            "entry": signal.plan.entry,
            "lots": signal.plan.lots,
            "sl": signal.plan.sl,
            "tp": signal.plan.tp,
            "magic": self.settings.risk.magic,
            "deviation": int(self.settings.protection.max_slippage_points),
            "ml_probability": signal.score.ml_probability,
            "grade": signal.grade.value,
            "comment": (self.settings.risk.comment + "-" + signal.signal_id)[:31],
            "breakeven_r": self.settings.risk.breakeven_r,
            "trail_start_r": self.settings.risk.trail_start_r,
            "trail_enabled": 1 if self.settings.risk.trail_enabled else 0,
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
    return {
        "action": signal.direction.value,
        "id": signal.signal_id,
        "symbol": settings.symbol,
        "lots": signal.plan.lots,
        "sl": signal.plan.sl,
        "tp": signal.plan.tp,
        "entry": signal.plan.entry,
        "direction": signal.direction.value,
    }


class Mql5PaperExecutor:
    """Mirrors the EA protocol without MetaEditor: read command.json, write status.json."""

    def __init__(self, settings: Settings, bid: float = 2000.0, ask: float = 2000.25):
        self.bridge = FileBridge(settings)
        self.settings = settings
        self.bid = bid
        self.ask = ask
        self.last_id = ""
        self.positions: list[dict[str, Any]] = []
        self._ticket = 1000

    def process_once(self) -> dict[str, Any]:
        if not self.bridge.command_path.exists():
            return self._status("idle", "no_command")
        try:
            cmd = json.loads(self.bridge.command_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return self._write_status(False, 0, 0.0, 0.0, 0.0, "bad_json", "")
        action = str(cmd.get("action") or "")
        cmd_id = str(cmd.get("id") or "")
        if not cmd_id or cmd_id == self.last_id:
            return self._status("duplicate", "duplicate_or_empty")
        if action in ("HEARTBEAT", "NONE"):
            self.last_id = cmd_id
            return self._write_status(True, 0, 0.0, 0.0, 0.0, "heartbeat", cmd_id)
        if action in ("BUY", "SELL"):
            if self.positions:
                self.last_id = cmd_id
                return self._write_status(False, 0, 0.0, 0.0, 0.0, "max_positions", cmd_id)
            lots = float(cmd.get("lots") or 0)
            sl = float(cmd.get("sl") or 0)
            tp = float(cmd.get("tp") or 0)
            if lots <= 0 or sl <= 0 or tp <= 0:
                self.last_id = cmd_id
                return self._write_status(False, 0, 0.0, sl, tp, "invalid_trade_plan", cmd_id)
            price = self.ask if action == "BUY" else self.bid
            self._ticket += 1
            self.positions.append(
                {
                    "ticket": self._ticket,
                    "direction": action,
                    "lots": lots,
                    "entry": price,
                    "sl": sl,
                    "tp": tp,
                    "signal_id": cmd_id,
                }
            )
            self.last_id = cmd_id
            return self._write_status(True, self._ticket, price, sl, tp, "filled", cmd_id)
        if action == "MODIFY":
            ticket = int(cmd.get("ticket") or 0)
            sl = float(cmd.get("sl") or 0)
            tp = float(cmd.get("tp") or 0)
            for pos in self.positions:
                if pos["ticket"] == ticket:
                    pos["sl"] = sl
                    pos["tp"] = tp
                    self.last_id = cmd_id
                    return self._write_status(True, ticket, pos["entry"], sl, tp, "modified", cmd_id)
            self.last_id = cmd_id
            return self._write_status(False, ticket, 0.0, sl, tp, "modify_failed", cmd_id)
        self.last_id = cmd_id
        return self._write_status(False, 0, 0.0, 0.0, 0.0, "unknown_action", cmd_id)

    def _write_status(
        self, ok: bool, ticket: int, price: float, sl: float, tp: float, error: str, cmd_id: str
    ) -> dict[str, Any]:
        payload = {
            "connected": True,
            "python_fresh": True,
            "symbol": self.settings.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "spread": 25,
            "positions": len(self.positions),
            "last_command_id": cmd_id or self.last_id,
            "time": datetime.now(timezone.utc).isoformat(),
            "last_result": {
                "id": cmd_id,
                "ok": ok,
                "ticket": ticket,
                "price": price,
                "sl": sl,
                "tp": tp,
                "error": error,
            },
        }
        tmp = self.bridge.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.bridge.status_path)
        return payload

    def _status(self, error: str, _msg: str) -> dict[str, Any]:
        return self._write_status(False, 0, 0.0, 0.0, 0.0, error, self.last_id)
