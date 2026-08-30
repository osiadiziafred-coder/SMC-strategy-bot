import numpy as np

from features import FEATURE_NAMES, sanitize_features
from smc_robot.config import Settings
from smc_robot.data.history import training_frames
from smc_robot.journal import DecisionJournal
from smc_robot.models import Decision, Direction, ScoreBreakdown, SetupGrade
from smc_robot.scoring import SetupScorer, explain_prediction
from smc_robot.scoring.dataset import build_labeled_dataset
from smc_robot.scoring.train import train_model


def test_sanitize_replaces_invalid_values():
    dirty = {name: 0.0 for name in FEATURE_NAMES}
    dirty["atr_ratio"] = float("nan")
    dirty["momentum"] = float("inf")
    clean = sanitize_features(dirty)
    assert clean["atr_ratio"] == 0.0
    assert clean["momentum"] == 0.0
    assert all(np.isfinite(v) for v in clean.values())


def test_historical_dataset_is_time_ordered_and_labeled(tmp_path):
    h1, m30, m15 = training_frames(n=220, seed=4)
    X, y, meta = build_labeled_dataset(
        h1, m30, m15, settings=Settings(), start_index=80, step=4, horizon=10
    )
    assert X.ndim == 2
    assert X.shape[1] == len(FEATURE_NAMES)
    assert len(y) == len(meta) == len(X)
    times = [row["time"] for row in meta]
    assert times == sorted(times)
    if len(set(y.tolist())) >= 2:
        path = tmp_path / "hist.joblib"
        model = train_model(X, y, path)
        proba = model.predict_proba(X[:1])[0]
        assert len(proba) >= 2
        assert 0.0 <= float(proba[1]) <= 1.0


def test_scorer_reports_buy_and_sell_and_explanation(tmp_path):
    rng = np.random.default_rng(2)
    X = rng.normal(size=(80, len(FEATURE_NAMES)))
    y = (X[:, 3] + X[:, 11] > 0).astype(int)
    y[0], y[1] = 0, 1
    path = tmp_path / "both.joblib"
    train_model(X, y, path)
    settings = Settings()
    settings.scoring.model_path = str(path)
    scorer = SetupScorer(settings)
    dummy = {name: 0.0 for name in FEATURE_NAMES}
    dummy["h1_aligned"] = 1.0
    dummy["sweep"] = 1.0
    dummy["m15_mss"] = 1.0
    p_buy = scorer.predict_success(dummy)
    dummy["h1_aligned"] = -1.0
    p_sell = scorer.predict_success(dummy)
    assert p_buy is not None and p_sell is not None
    explained = explain_prediction(dummy, scorer.importances)
    assert explained
    assert "feature" in explained[0]


def test_journal_writes_readable_ml_summary(tmp_path):
    journal = DecisionJournal(str(tmp_path))
    score = ScoreBreakdown(
        total=80,
        rule_score=80,
        ml_probability=0.86,
        ml_buy_probability=0.86,
        ml_sell_probability=0.12,
        grade=SetupGrade.A,
        features={"sweep": 1.0, "ob_interact": 1.0, "fvg_interact": 1.0, "m15_mss": 1.0},
    )
    journal.write("XAUUSDm", Decision(action="buy", reason="take_setup", score=score))
    text = (tmp_path / "decisions.log").read_text(encoding="utf-8")
    assert "ML_BUY=0.86" in text
    assert "ML_SELL=0.12" in text
    assert "Decision=BUY" in text
