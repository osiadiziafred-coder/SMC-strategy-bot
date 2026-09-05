"""File-based command bridge between the Python brain and the MQL5 EA.

Python writes ``command.json``; the EA reads it, executes at most once (commands
carry a unique ``id``) and reports back in ``status.json`` which Python reads.

Responsibilities handled here:

* Atomic JSON writes (temp file + ``os.replace``) so the EA never reads a
  half-written command.
* A unique command ``id`` and monotonically increasing ``seq`` per command.
* A ``heartbeat`` timestamp on every command, plus :meth:`touch_heartbeat` to
  refresh liveness *without* changing the pending command's id (so the EA does
  not re-execute it).
* De-duplication so the brain never spams the same setup repeatedly.
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

    # -- low-level io ------------------------------------------------------
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

    # -- commands ----------------------------------------------------------
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
        }

    def write_trade_command(self, action: str, lots: float, sl: float, tp: float,
                            entry: float, breakeven_r: float, trail_start_r: float,
                            trail_enabled: bool) -> dict:
        if action not in ("BUY", "SELL"):
            raise ValueError("write_trade_command only supports BUY/SELL")
        cmd = self._new_envelope(action)
        cmd.update(
            {
                "lots": round(float(lots), 2),
                "entry": round(float(entry), 3),
                "sl": round(float(sl), 3),
                "tp": round(float(tp), 3),
                "breakeven_r": float(breakeven_r),
                "trail_start_r": float(trail_start_r),
                "trail_enabled": bool(trail_enabled),
            }
        )
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
        """Refresh liveness. If a command already exists, only its heartbeat is
        updated (id preserved) so a pending trade is not lost or re-executed."""

        existing = self._read_json(self.cfg.command_path)
        if existing:
            existing["heartbeat"] = time.time()
            self._atomic_write(self.cfg.command_path, existing)
            return existing
        return self.write_simple_command("HEARTBEAT")

    # alias used by the live loop for clarity
    touch_heartbeat = send_heartbeat

    # -- de-duplication ----------------------------------------------------
    def _signature(self, direction: str, entry: float, sl: float) -> tuple:
        return (direction, round(entry, 1), round(sl, 1))

    def should_send(self, direction: str, entry: float, sl: float, cooldown_sec: float = 300.0) -> bool:
        sig = self._signature(direction, entry, sl)
        now = time.time()
        if sig == self._last_signature and (now - self._last_signature_time) < cooldown_sec:
            return False
        return True

    def mark_sent(self, direction: str, entry: float, sl: float) -> None:
        self._last_signature = self._signature(direction, entry, sl)
        self._last_signature_time = time.time()

    # -- status ------------------------------------------------------------
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
