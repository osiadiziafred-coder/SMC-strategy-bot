import json

import pytest

from ml_scalper.brain import ScalperBrain
from ml_scalper.config import Config
from ml_scalper.ml_model import ScalperModels, TradeScore
from ml_scalper.mt5_connector import SyntheticConnector
from ml_scalper.train_model import train


def _cfg(tmp_path, symbol="Volatility 75 Index", **kw):
    cfg = Config.for_symbol(
        symbol,
        data_source="synthetic",
        train_bars=2500,
        live_bars=350,
        n_estimators=60,
        model_dir=tmp_path / "models",
        bridge_dir=tmp_path / "ml_scalper_bridge",
        log_dir=tmp_path / "logs",
        **kw,
    )
    cfg.ensure_dirs()
    return cfg


@pytest.fixture(scope="module")
def trained_v75(tmp_path_factory):
    root = tmp_path_factory.mktemp("v75")
    cfg = _cfg(root)
    meta = train(cfg, test_frac=0.2, n_splits=2, seed=7)
    return cfg, meta


def test_train_saves_dual_head_model(trained_v75):
    cfg, meta = trained_v75
    assert cfg.model_path.exists()
    assert meta["n_out_samples"] > 400
    assert meta["outcome_importance"]
    assert 0.0 <= meta["metrics"]["outcome_holdout_accuracy"] <= 1.0
    assert "threshold_search" in meta
    model = ScalperModels.load(cfg.model_path)
    assert model.direction.backend
    assert model.outcome.backend


def test_loaded_model_outputs_three_way_score(trained_v75):
    cfg, _ = trained_v75
    model = ScalperModels.load(cfg.model_path)
    conn = SyntheticConnector(cfg, seed=13)
    conn.connect()
    from ml_scalper.features import build_live_features

    last, buy, sell = build_live_features(
        conn.get_rates("M15", 300), conn.get_rates("M5", 300), conn.get_rates("M1", 300), cfg
    )
    score = model.predict(last, buy, sell)
    for p in (score.p_buy, score.p_sell, score.p_none, score.p_tp_buy, score.p_tp_sell):
        assert 0.0 <= p <= 1.0
    assert abs(score.p_buy + score.p_sell + score.p_none - 1.0) < 1e-6
    assert len(model.outcome.explain(buy)) > 0


def test_brain_replay_runs(trained_v75):
    cfg, _ = trained_v75
    conn = SyntheticConnector(cfg, seed=21, balance=1000.0)
    brain = ScalperBrain(cfg, connector=conn, apply_recommended=False)
    counts = brain.run_replay(steps=80, warmup=280)
    assert sum(counts.values()) > 0
    assert set(counts).issubset({"BUY", "SELL", "NONE"})


def test_brain_writes_buy_when_filters_and_ml_agree(trained_v75, monkeypatch):
    cfg, _ = trained_v75
    conn = SyntheticConnector(cfg, seed=3, balance=1000.0)
    brain = ScalperBrain(cfg, connector=conn, apply_recommended=False)
    cfg.ml_min_confidence = 0.70
    cfg.min_outcome_prob = 0.55
    brain.model.predict = lambda *a, **k: TradeScore(0.82, 0.11, 0.07, 0.74, 0.22)
    brain.model.outcome.explain = lambda *a, **k: [("m5_momentum", 0.4, 0.12)]
    monkeypatch.setattr(
        "ml_scalper.brain.live_setup_flags",
        lambda *a, **k: {
            "m15_bull": True,
            "m15_bear": False,
            "near_ma": True,
            "pullback_buy": True,
            "pullback_sell": False,
            "momentum_up": True,
            "momentum_down": False,
            "buy_setup": True,
            "sell_setup": False,
        },
    )
    monkeypatch.setattr("ml_scalper.brain.abnormal_conditions", lambda *a, **k: None)
    decision = brain.run_cycle()
    assert decision.action == "BUY"
    cmd = json.loads(cfg.command_path.read_text())
    assert cmd["action"] == "BUY"
    assert cmd["symbol"] == cfg.symbol
    assert cmd["lots"] > 0
    assert cmd["sl"] < cmd["entry"] < cmd["tp"]
    assert cmd["p_buy"] == 0.82


def test_separate_model_paths_per_symbol(tmp_path):
    a = _cfg(tmp_path, "Volatility 50 (1s) Index")
    b = _cfg(tmp_path, "XAUUSD")
    assert a.model_filename != b.model_filename
    assert "v50" in a.model_filename
    assert "xau" in b.model_filename
