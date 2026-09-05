"""File-based command bridge: Python brain → MQL5 EA.

Python writes ``command.json``; the EA executes at most once per unique ``id``
and reports ``status.json``. Python never sends broker orders itself.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from .config import Config

VALID_ACTIONS = {"BUY", "SELL", "MODIFY", "CLOSE", "HEARTBEAT", "NONE"}


class CommandManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.bridge_dir = Path(cfg.bridge_dir)
        self.bridge_dir.mkdir(parents=True, exist_ok=True)
        self._seq = 0
        self._last_signature: tuple | None = None
        self._last_signature_time = 0.0

    def _atomic_write(self, path: Path, obj: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2)
        os.replace(tmp, path)

    def _read_json(self, path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _lot_decimals(self) -> int:
        step = self.cfg.lot_step or 0.01
        if step >= 1:
            return 0
        s = f"{step:.10f}".rstrip("0")
        return len(s.split(".")[1]) if "." in s else 2

    def _new_envelope(self, action: str) -> dict:
        self._seq += 1
        now = time.time()
        return {
            "id": uuid.uuid4().hex,
            "seq": self._seq,
            "action": action,
            "symbol": self.cfg.symbol,
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)),
            "heartbeat": now,
            "system": "ml_scalper",
        }

    def write_trade_command(
        self,
        action: str,
        lots: float,
        sl: float,
        tp: float,
        entry: float,
        breakeven_r: float,
        trail_start_r: float,
        trail_enabled: bool,
        extra: dict | None = None,
    ) -> dict:
        if action not in ("BUY", "SELL"):
            raise ValueError("write_trade_command only supports BUY/SELL")
        digits = int(self.cfg.digits)
        cmd = self._new_envelope(action)
        cmd.update(
            {
                "lots": round(float(lots), self._lot_decimals()),
                "entry": round(float(entry), digits),
                "sl": round(float(sl), digits),
                "tp": round(float(tp), digits),
                "breakeven_r": float(breakeven_r),
                "trail_start_r": float(trail_start_r),
                "trail_enabled": bool(trail_enabled),
                "risk_reward": float(self.cfg.risk_reward),
            }
        )
        if extra:
            cmd.update(extra)
        self._atomic_write(self.cfg.command_path, cmd)
        return cmd

    def write_simple_command(self, action: str, **extra) -> dict:
        if action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {action}")
        cmd = self._new_envelope(action)
        cmd.update(extra)
        self._atomic_write(self.cfg.command_path, cmd)
        return cmd

    def send_heartbeat(self) -> dict:
        existing = self._read_json(self.cfg.command_path)
        if existing:
            existing["heartbeat"] = time.time()
            self._atomic_write(self.cfg.command_path, existing)
            return existing
        return self.write_simple_command("HEARTBEAT")

    touch_heartbeat = send_heartbeat

    def _signature(self, direction: str, entry: float, sl: float) -> tuple:
        return (direction, round(entry, max(0, self.cfg.digits - 1)), round(sl, max(0, self.cfg.digits - 1)))

    def should_send(self, direction: str, entry: float, sl: float, cooldown_sec: float | None = None) -> bool:
        cooldown = self.cfg.command_cooldown_sec if cooldown_sec is None else cooldown_sec
        sig = self._signature(direction, entry, sl)
        now = time.time()
        if sig == self._last_signature and (now - self._last_signature_time) < cooldown:
            return False
        return True

    def mark_sent(self, direction: str, entry: float, sl: float) -> None:
        self._last_signature = self._signature(direction, entry, sl)
        self._last_signature_time = time.time()

    def read_status(self) -> dict:
        return self._read_json(self.cfg.status_path)

    def open_positions(self, status: dict | None = None) -> int:
        status = status if status is not None else self.read_status()
        positions = status.get("positions", [])
        return len([p for p in positions if p.get("symbol") == self.cfg.symbol])

    def is_ea_alive(self, status: dict | None = None) -> bool:
        status = status if status is not None else self.read_status()
        hb = status.get("heartbeat")
        if hb is None:
            return False
        return (time.time() - float(hb)) <= self.cfg.python_timeout_sec
