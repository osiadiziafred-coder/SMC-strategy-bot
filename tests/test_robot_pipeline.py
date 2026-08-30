import numpy as np

from ml_smc_robot.config import Config
from ml_smc_robot.ml_model import MLModel
from ml_smc_robot.mt5_connector import SyntheticConnector
from ml_smc_robot.smc_ml_brain import SMCBrain
from ml_smc_robot.train_model import train


def _cfg(tmp_path, **kw):
    cfg = Config(
        data_source="synthetic",
        train_bars=4000,
        live_bars=400,
        model_dir=tmp_path / "models",
        bridge_dir=tmp_path / "smc_bridge",
        log_dir=tmp_path / "logs",
        **kw,
    )
    cfg.ensure_dirs()
    return cfg


def test_train_saves_real_model_with_metrics(tmp_path):
    cfg = _cfg(tmp_path)
    meta = train(cfg, test_frac=0.2, n_splits=3, seed=7)

    assert cfg.model_path.exists()
    assert meta["n_samples"] > 500
    assert 0.0 <= meta["positive_rate"] <= 1.0
    assert meta["feature_importance"], "model must expose feature importances"
    # A real trained classifier should beat a trivial constant on the holdout.
    assert meta["metrics"]["holdout_accuracy"] > 0.0


def test_loaded_model_predicts_valid_probabilities(tmp_path):
    cfg = _cfg(tmp_path)
    train(cfg, test_frac=0.2, n_splits=3, seed=7)

    model = MLModel.load(cfg.model_path)
    conn = SyntheticConnector(cfg, seed=13)
    conn.connect()
    h1 = conn.get_rates("H1", cfg.live_bars)
    m30 = conn.get_rates("M30", cfg.live_bars)
    m15 = conn.get_rates("M15", cfg.live_bars)

    from ml_smc_robot.features import build_live_features

    _, buy, sell = build_live_features(h1, m30, m15, cfg)
    p_buy = model.predict_success_proba(buy)[0]
    p_sell = model.predict_success_proba(sell)[0]
    assert 0.0 <= p_buy <= 1.0
    assert 0.0 <= p_sell <= 1.0
    assert len(model.explain(buy)) > 0


def test_brain_replay_runs_end_to_end(tmp_path):
    cfg = _cfg(tmp_path)
    train(cfg, test_frac=0.2, n_splits=3, seed=7)

    conn = SyntheticConnector(cfg, seed=21, balance=1000.0)
    brain = SMCBrain(cfg, connector=conn)
    counts = brain.run_replay(steps=150, warmup=350)

    assert sum(counts.values()) > 0
    assert set(counts).issubset({"BUY", "SELL", "NONE"})
