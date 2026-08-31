"""Read status.json written by the MQL5 bridge and wait for execution results."""

from __future__ import annotations

from typing import Any

from python_smc_ml_robot._paths import ROOT  # noqa: F401

from smc_robot.bridge import FileBridge


class StatusReader:
    def __init__(self, bridge: FileBridge):
        self.bridge = bridge

    def read(self) -> dict[str, Any]:
        return self.bridge.read_status()

    def connected(self) -> bool:
        return self.bridge.connected()

    def last_execution(self) -> dict[str, Any]:
        status = self.read()
        result = status.get("last_result") or {}
        if result:
            return result
        return {
            "id": status.get("last_command_id"),
            "retcode": status.get("retcode"),
            "error": status.get("error"),
            "ticket": status.get("ticket"),
            "sl": status.get("sl"),
            "tp": status.get("tp"),
            "profit": status.get("profit"),
        }

    def wait_for_result(self, command_id: str, timeout: float | None = None) -> dict[str, Any]:
        return self.bridge.wait_for_result(command_id, timeout=timeout)


__all__ = ["StatusReader"]
