from ml_scalper.config import Config
from ml_scalper.risk_manager import ProtectionState, RiskManager


def _si(v75=True):
    if v75:
        return {"point": 0.01, "digits": 2, "volume_min": 0.001, "volume_max": 50.0, "volume_step": 0.001, "trade_contract_size": 1.0}
    return {"point": 0.01, "digits": 2, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01, "trade_contract_size": 100.0}


def test_lot_sizing_v75_uses_thousandths():
    rm = RiskManager(Config.for_symbol("Volatility 75 Index"))
    si = _si(True)
    assert rm.lot_size(100, si) == 0.001
    assert rm.lot_size(1000, si) == 0.01


def test_lot_sizing_xauusd():
    rm = RiskManager(Config.for_symbol("XAUUSD"))
    si = _si(False)
    assert rm.lot_size(100, si) == 0.01
    assert rm.lot_size(1000, si) == 0.10


def test_buy_and_sell_atr_stops_are_1_to_2():
    rm = RiskManager(Config.for_symbol("Volatility 75 Index"))
    si = _si(True)
    sl, tp, risk = rm.compute_sl_tp("BUY", 100000.0, atr=20.0, symbol_info=si)
    assert sl < 100000.0 < tp
    assert abs((tp - 100000.0) / risk - 2.0) < 0.01
    sl, tp, risk = rm.compute_sl_tp("SELL", 100000.0, atr=20.0, symbol_info=si)
    assert tp < 100000.0 < sl
    assert abs((100000.0 - tp) / risk - 2.0) < 0.01
    assert rm.validate_rr("SELL", 100000.0, sl, tp)


def test_daily_and_streak_halts():
    cfg = Config.for_symbol("Volatility 75 Index", max_daily_loss_pct=3.0, max_consecutive_losses=3)
    rm = RiskManager(cfg, state=ProtectionState(day="2099-01-01", starting_balance=1000.0))
    # force "today" by writing state after sync using a fake status
    rm.state.starting_balance = 1000.0
    rm.state.realized_pnl = -40.0  # 4%
    # protection_block resets day to real UTC today — so set day to today via calling then overwrite
    rm.protection_block(1000.0)
    rm.state.realized_pnl = -40.0
    rm.state.starting_balance = 1000.0
    assert rm.protection_block(1000.0) is not None

    rm2 = RiskManager(cfg)
    rm2.protection_block(1000.0)
    rm2.state.consecutive_losses = 3
    assert "consecutive" in (rm2.protection_block(1000.0) or "")


def test_gates():
    rm = RiskManager(Config.for_symbol("XAUUSD"))
    assert rm.check_spread(20) is True
    assert rm.check_spread(90) is False
    assert rm.can_open(0) is True
    assert rm.can_open(1) is False
