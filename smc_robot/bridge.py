"""File-based Python ↔ MQL5 command/status protocol.

Python writes command.json. The MQL5 EA validates, executes, and writes status.json.
The EA does not invent its own entries.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smc_robot.config import Settings
from smc_robot.models import Signal

_COMMAND_SEQ = 0


def new_command_id(kind: str = "trade", when: datetime | None = None, salt: str = "") -> str:
    """Unique command IDs, e.g. trade_20260831_190700_001.

    Trade IDs with a salt are stable for the same bar/setup so the robot
    does not re-send the same order. Heartbeat/NONE IDs stay unique.
    """
    global _COMMAND_SEQ
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    if salt:
        digest = hashlib.md5(f"{kind}:{stamp}:{salt}".encode("utf-8")).hexdigest()
        tail = int(digest, 16) % 1000
    else:
        _COMMAND_SEQ = (_COMMAND_SEQ + 1) % 1000
        tail = _COMMAND_SEQ
    return f"{kind}_{stamp}_{tail:03d}"


class FileBridge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.directory = Path(settings.bridge.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.command_path = self.directory / settings.bridge.command_file
        self.status_path = self.directory / settings.bridge.status_file
        self._last_sent = ""

    def send_none(self, reason: str = "no_setup") -> str:
        cmd_id = new_command_id("none")
        self._write_command(
            {
                "action": "NONE",
                "id": cmd_id,
                "symbol": self.settings.symbol,
                "reason": reason,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )
        return cmd_id

    def heartbeat(self) -> None:
        self._write_command(
            {
                "action": "HEARTBEAT",
                "id": new_command_id("heartbeat"),
                "symbol": self.settings.symbol,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )

    def send_signal(self, signal: Signal) -> str:
        command = {
            "action": signal.direction.value,
            "id": signal.signal_id,
            "symbol": self.settings.symbol,
            "direction": signal.direction.value,
            "entry": signal.plan.entry,
            "lots": signal.plan.lots,
            "lot": signal.plan.lots,
            "sl": signal.plan.sl,
            "tp": signal.plan.tp,
            "magic": self.settings.risk.magic,
            "deviation": int(self.settings.protection.max_slippage_points),
            "ml_probability": signal.score.ml_probability,
            "smc_score": signal.score.total,
            "grade": signal.grade.value,
            "reason": signal.reason,
            "comment": (self.settings.risk.comment + "-" + signal.signal_id)[:31],
            "breakeven_r": self.settings.risk.breakeven_r,
            "trail_start_r": self.settings.risk.trail_start_r,
            "ml_buy_probability": signal.score.ml_buy_probability,
            "ml_sell_probability": signal.score.ml_sell_probability,
            "trail_enabled": bool(self.settings.risk.trail_enabled),
            "time": datetime.now(timezone.utc).isoformat(),
        }
        self._write_command(command)
        self._last_sent = signal.signal_id
        return signal.signal_id

    def send_modify(self, ticket: int, sl: float, tp: float, signal_id: str) -> None:
        self._write_command(
            {
                "action": "MODIFY",
                "id": f"{signal_id}-mod-{int(time.time() * 1000)}",
                "symbol": self.settings.symbol,
                "ticket": ticket,
                "sl": sl,
                "tp": tp,
                "magic": self.settings.risk.magic,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )

    def send_close(self, ticket: int, signal_id: str) -> None:
        self._write_command(
            {
                "action": "CLOSE",
                "id": f"{signal_id}-close-{int(time.time() * 1000)}",
                "symbol": self.settings.symbol,
                "ticket": ticket,
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

    def wait_for_result(
        self,
        command_id: str,
        timeout: float | None = None,
        poll: float = 0.1,
    ) -> dict[str, Any]:
        limit = (
            self.settings.bridge.result_timeout_seconds if timeout is None else timeout
        )
        deadline = time.time() + max(0.0, limit)
        while time.time() <= deadline:
            result = self.last_result_for(command_id)
            if result is not None:
                return result
            time.sleep(poll)
        return {}

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
        "direction": signal.direction.value,
        "lots": signal.plan.lots,
        "sl": signal.plan.sl,
        "tp": signal.plan.tp,
        "entry": signal.plan.entry,
        "smc_score": signal.score.total,
        "reason": signal.reason,
    }


def sl_is_improvement(direction: str, new_sl: float, current_sl: float) -> bool:
    if new_sl <= 0:
        return False
    if current_sl <= 0:
        return True
    if direction == "BUY":
        return new_sl > current_sl + 1e-8
    return new_sl < current_sl - 1e-8


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
        self._last_python = 0.0
        self._last_result: dict[str, Any] = {}
        self.trail_on = bool(settings.risk.trail_enabled)

    def python_fresh(self) -> bool:
        if self._last_python <= 0:
            return False
        return (time.time() - self._last_python) <= self.settings.bridge.python_timeout_seconds

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
            self._last_python = time.time()
            self.last_id = cmd_id
            return self._write_status(True, 0, 0.0, 0.0, 0.0, "heartbeat", cmd_id)
        if action in ("BUY", "SELL") and not self.python_fresh():
            self.last_id = cmd_id
            return self._write_status(False, 0, 0.0, 0.0, 0.0, "python_disconnected", cmd_id)
        self._last_python = time.time()
        if "trail_enabled" in cmd:
            flag = cmd.get("trail_enabled")
            self.trail_on = bool(flag) and flag not in (0, "0", "false", "False")
        if action in ("BUY", "SELL"):
            if self.positions:
                self.last_id = cmd_id
                return self._write_status(False, 0, 0.0, 0.0, 0.0, "max_positions", cmd_id)
            lots = float(cmd.get("lots") or cmd.get("lot") or 0)
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
                    if not sl_is_improvement(pos["direction"], sl, float(pos["sl"])):
                        self.last_id = cmd_id
                        return self._write_status(
                            False, ticket, pos["entry"], sl, tp, "sl_would_loosen", cmd_id
                        )
                    pos["sl"] = sl
                    if tp > 0:
                        pos["tp"] = tp
                    self.last_id = cmd_id
                    return self._write_status(True, ticket, pos["entry"], sl, pos["tp"], "modified", cmd_id)
            self.last_id = cmd_id
            return self._write_status(False, ticket, 0.0, sl, tp, "modify_failed", cmd_id)
        if action == "CLOSE":
            ticket = int(cmd.get("ticket") or 0)
            before = len(self.positions)
            self.positions = [p for p in self.positions if p["ticket"] != ticket]
            self.last_id = cmd_id
            if len(self.positions) == before:
                return self._write_status(False, ticket, 0.0, 0.0, 0.0, "close_failed", cmd_id)
            return self._write_status(True, ticket, 0.0, 0.0, 0.0, "closed", cmd_id)
        self.last_id = cmd_id
        return self._write_status(False, 0, 0.0, 0.0, 0.0, "unknown_action", cmd_id)

    def _write_status(
        self, ok: bool, ticket: int, price: float, sl: float, tp: float, error: str, cmd_id: str
    ) -> dict[str, Any]:
        if cmd_id:
            self._last_result = {
                "id": cmd_id,
                "ok": ok,
                "ticket": ticket,
                "price": price,
                "sl": sl,
                "tp": tp,
                "error": error,
            }
        pos = self.positions[0] if self.positions else {}
        payload = {
            "connected": True,
            "python_fresh": self.python_fresh(),
            "trail_on": self.trail_on,
            "symbol": self.settings.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "spread": 25,
            "positions": len(self.positions),
            "ticket": pos.get("ticket", ticket),
            "sl": pos.get("sl", sl),
            "tp": pos.get("tp", tp),
            "profit": 0.0,
            "last_command_id": cmd_id or self.last_id,
            "retcode": 0 if ok else 1,
            "error": error,
            "time": datetime.now(timezone.utc).isoformat(),
            "last_result": self._last_result,
        }
        tmp = self.bridge.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.bridge.status_path)
        return payload

    def _status(self, error: str, _msg: str) -> dict[str, Any]:
        return self._write_status(False, 0, 0.0, 0.0, 0.0, error, self.last_id)
