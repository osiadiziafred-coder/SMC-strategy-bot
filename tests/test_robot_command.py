import json
import time

from ml_smc_robot.command_manager import CommandManager
from ml_smc_robot.config import Config


def _cfg(tmp_path):
    return Config(bridge_dir=tmp_path / "smc_bridge")


def test_trade_command_has_unique_id_and_fields(tmp_path):
    cm = CommandManager(_cfg(tmp_path))
    c1 = cm.write_trade_command("BUY", 0.01, 3400.0, 3420.0, 3410.0, 1.0, 1.5, True)
    c2 = cm.write_trade_command("SELL", 0.02, 3450.0, 3410.0, 3430.0, 1.0, 1.5, True)
    assert c1["id"] != c2["id"]
    assert c1["seq"] < c2["seq"]
    for key in ("id", "action", "symbol", "lots", "sl", "tp", "breakeven_r", "trail_start_r", "trail_enabled"):
        assert key in c1

    on_disk = json.loads((tmp_path / "smc_bridge" / "command.json").read_text())
    assert on_disk["action"] == "SELL"


def test_heartbeat_preserves_pending_command_id(tmp_path):
    cm = CommandManager(_cfg(tmp_path))
    cmd = cm.write_trade_command("BUY", 0.01, 3400.0, 3420.0, 3410.0, 1.0, 1.5, True)
    original_id = cmd["id"]
    hb = cm.send_heartbeat()
    assert hb["id"] == original_id  # heartbeat must NOT change a pending command's id
    assert hb["action"] == "BUY"


def test_deduplication_cooldown(tmp_path):
    cm = CommandManager(_cfg(tmp_path))
    assert cm.should_send("BUY", 3400.0, 3390.0) is True
    cm.mark_sent("BUY", 3400.0, 3390.0)
    assert cm.should_send("BUY", 3400.0, 3390.0) is False
    # Different setup is allowed.
    assert cm.should_send("SELL", 3400.0, 3410.0) is True


def test_status_reading(tmp_path):
    cfg = _cfg(tmp_path)
    cm = CommandManager(cfg)
    (tmp_path / "smc_bridge").mkdir(parents=True, exist_ok=True)
    status = {
        "heartbeat": time.time(),
        "positions": [{"symbol": cfg.symbol, "type": "BUY"}],
        "last_executed_id": "abc",
    }
    cfg.status_path.write_text(json.dumps(status))
    assert cm.open_positions() == 1
    assert cm.is_ea_alive() is True
