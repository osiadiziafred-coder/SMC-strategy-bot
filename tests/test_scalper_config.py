from ml_scalper.config import Config, instrument_slug, resolve_symbol
from ml_scalper.indicators import atr, ema, rsi, session_vwap


def test_resolve_symbol_aliases():
    assert resolve_symbol("V75") == "Volatility 75 Index"
    assert resolve_symbol("Volatility 50 (1s)") == "Volatility 50 (1s) Index"
    assert resolve_symbol("XAUUSDm") == "XAUUSD"
    assert resolve_symbol("GOLD") == "XAUUSD"


def test_per_instrument_settings_differ():
    v50 = Config.for_symbol("Volatility 50 (1s) Index")
    v75 = Config.for_symbol("Volatility 75 Index")
    xau = Config.for_symbol("XAUUSD")
    assert instrument_slug(v50.symbol) == "v50_1s"
    assert v50.model_filename != v75.model_filename != xau.model_filename
    assert v50.require_m1_confirm is False
    assert xau.session_vwap is True
    assert v75.session_vwap is False
    assert xau.max_spread_points < v75.max_spread_points
    assert xau.min_lot == 0.01
    assert v50.min_lot == 0.001
    assert v50.atr_sl_mult != v75.atr_sl_mult or v50.label_horizon != v75.label_horizon


def test_v50_never_requires_m1_as_hard_gate():
    cfg = Config.for_symbol("Volatility 50 (1s) Index")
    assert cfg.require_m1_confirm is False
    assert cfg.use_m1_precision is True
    assert cfg.regime_timeframe == "M15"
    assert cfg.setup_timeframe == "M5"
