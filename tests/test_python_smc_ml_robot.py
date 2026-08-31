import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from python_smc_ml_robot.command_bridge import FileBridge, new_command_id
from python_smc_ml_robot.config import ALLOWED_ML_THRESHOLDS, MIN_ML_SCORE, Settings, load_config
from python_smc_ml_robot.feature_engine import FEATURE_NAMES
from python_smc_ml_robot.market_data import inspect_market, verify_symbol
from python_smc_ml_robot.ml_model import SetupScorer
from python_smc_ml_robot.status_reader import StatusReader
from smc_robot.broker.paper import PaperBroker
from smc_robot.data.history import training_frames
from smc_robot.scoring.dataset import build_labeled_dataset
from smc_robot.scoring.train import train_model


def test_spec_package_imports():
    import python_smc_ml_robot.command_bridge as command_bridge
    import python_smc_ml_robot.feature_engine as feature_engine
    import python_smc_ml_robot.fvg as fvg
    import python_smc_ml_robot.liquidity as liquidity
    import python_smc_ml_robot.logger as logger
    import python_smc_ml_robot.main as main
    import python_smc_ml_robot.market_structure as market_structure
    import python_smc_ml_robot.ml_model as ml_model
    import python_smc_ml_robot.mt5_connector as mt5_connector
    import python_smc_ml_robot.order_blocks as order_blocks
    import python_smc_ml_robot.risk_manager as risk_manager
    import python_smc_ml_robot.signal_engine as signal_engine
    import python_smc_ml_robot.smc_engine as smc_engine
    import python_smc_ml_robot.status_reader as status_reader

    assert command_bridge.FileBridge
    assert feature_engine.FEATURE_NAMES
    assert fvg.detect_fvgs
    assert liquidity.detect_sweeps
    assert logger.configure_logging
    assert main.main
    assert market_structure.detect_structure_events
    assert ml_model.train_model
    assert mt5_connector.MT5Broker
    assert order_blocks.detect_order_blocks
    assert risk_manager.lots_from_balance
    assert signal_engine.SmcEngine
    assert smc_engine.analyze_timeframe
    assert status_reader.StatusReader
    assert MIN_ML_SCORE == 0.70
    assert 0.70 in ALLOWED_ML_THRESHOLDS


def test_min_ml_score_alias_from_yaml_and_constructor():
    from smc_robot.config import ScoringConfig

    cfg = ScoringConfig(min_ml_score=0.80)
    assert cfg.ml_min_probability == 0.80
    assert MIN_ML_SCORE == 0.70
    loaded = load_config()
    assert loaded.scoring.ml_min_probability == 0.70
    assert loaded.scoring.min_ml_score == 0.70


def test_command_ids_match_spec_and_are_stable_for_trades():
    when = datetime(2026, 8, 31, 19, 7, 0, tzinfo=timezone.utc)
    salt = "XAUUSDm:BUY:2026-08-31T19:07:00+00:00"
    first = new_command_id("trade", when=when, salt=salt)
    second = new_command_id("trade", when=when, salt=salt)
    assert first == second
    assert re.fullmatch(r"trade_\d{8}_\d{6}_\d{3}", first)
    hb1 = new_command_id("heartbeat")
    hb2 = new_command_id("heartbeat")
    assert hb1 != hb2
    assert hb1.startswith("heartbeat_")


def test_verify_exact_symbol_and_snapshot():
    broker = PaperBroker(balance=500.0, bid=2340.12, ask=2340.38)
    spec = verify_symbol(broker, "XAUUSDm")
    assert spec.name == "XAUUSDm"
    assert spec.bid == 2340.12
    assert spec.ask == 2340.38
    assert spec.point > 0
    assert spec.volume_min > 0
    assert spec.volume_step > 0
    assert spec.trade_mode == "full"
    snap_spec, quote, snap = inspect_market(broker, Settings())
    assert snap["symbol"] == "XAUUSDm"
    assert snap["digits"] == snap_spec.digits
    assert quote.ask >= quote.bid
    try:
        verify_symbol(broker, "GOLD")
        assert False, "expected missing GOLD"
    except RuntimeError as exc:
        assert "symbol_unavailable" in str(exc)


def test_status_reader_and_heartbeat_command(tmp_path: Path):
    settings = Settings()
    settings.bridge.directory = str(tmp_path)
    bridge = FileBridge(settings)
    cmd_id = bridge.send_none("no_setup")
    assert re.search(r"none_\d{8}_\d{6}_\d{3}", cmd_id)
    from smc_robot.bridge import Mql5PaperExecutor

    executor = Mql5PaperExecutor(settings)
    executor.process_once()
    status = StatusReader(bridge).read()
    assert status["connected"] is True
    assert "python_fresh" in status
    assert "profit" in status
    assert status["symbol"] == "XAUUSDm"


def test_pkl_model_loads_and_dataset_records_outcomes(tmp_path: Path):
    rng = np.random.default_rng(5)
    X = rng.normal(size=(80, len(FEATURE_NAMES)))
    y = (X[:, 3] + X[:, 11] > 0).astype(int)
    y[0], y[1] = 0, 1
    joblib_path = tmp_path / "smc_scorer.joblib"
    train_model(X, y, joblib_path)
    assert (tmp_path / "smc_model.pkl").exists()
    settings = Settings()
    settings.scoring.model_path = str(tmp_path / "missing.joblib")
    # sibling pkl next to a missing joblib should not load; point at the pkl
    settings.scoring.model_path = str(tmp_path / "smc_model.pkl")
    scorer = SetupScorer(settings)
    assert scorer._model is not None
    h1, m30, m15 = training_frames(n=180, seed=8)
    _X, _y, meta = build_labeled_dataset(h1, m30, m15, settings=Settings(), start_index=80, step=6)
    assert meta
    assert {"entry", "sl", "tp", "mfe", "mae", "tp_hit", "sl_hit", "outcome"} <= set(meta[0])


def test_balance_step_lot_size():
    from python_smc_ml_robot.risk_manager import SymbolSpec, lots_from_balance

    spec = SymbolSpec(name="XAUUSDm")
    assert lots_from_balance(100, spec) == 0.01
    assert lots_from_balance(200, spec) == 0.02
    assert lots_from_balance(500, spec) == 0.05
    assert lots_from_balance(1000, spec) == 0.10
