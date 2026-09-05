import json
import time

from ml_scalper.command_manager import CommandManager
from ml_scalper.config import Config


def _cfg(tmp_path, symbol="Volatility 75 Index"):
    return Config.for_symbol(symbol, bridge_dir=tmp_path / "ml_scalper_bridge")


def test_trade_command_unique_id_and_lot_precision(tmp_path):
    cm = CommandManager(_cfg(tmp_path))
    c1 = cm.write_trade_command("BUY", 0.003, 1000.0, 1020.0, 1010.0, 1.0, 1.5, True)
    c2 = cm.write_trade_command("SELL", 0.002, 1020.0, 1000.0, 1010.0, 1.0, 1.5, True)
    assert c1["id"] != c2["id"]
    assert c1["seq"] < c2["seq"]
    assert c1["lots"] == 0.003
    assert c1["system"] == "ml_scalper"
    on_disk = json.loads((tmp_path / "ml_scalper_bridge" / "command.json").read_text())
    assert on_disk["action"] == "SELL"


def test_heartbeat_preserves_pending_id(tmp_path):
    cm = CommandManager(_cfg(tmp_path))
    cmd = cm.write_trade_command("BUY", 0.001, 1000.0, 1020.0, 1010.0, 1.0, 1.5, True)
    hb = cm.send_heartbeat()
    assert hb["id"] == cmd["id"]
    assert hb["action"] == "BUY"


def test_dedup_and_status(tmp_path):
    cfg = _cfg(tmp_path)
    cm = CommandManager(cfg)
    assert cm.should_send("BUY", 1000.0, 990.0) is True
    cm.mark_sent("BUY", 1000.0, 990.0)
    assert cm.should_send("BUY", 1000.0, 990.0) is False
    status = {"heartbeat": time.time(), "positions": [{"symbol": cfg.symbol, "type": "BUY"}]}
    cfg.status_path.write_text(json.dumps(status))
    assert cm.open_positions() == 1
    assert cm.is_ea_alive() is True
