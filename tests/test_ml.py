from pathlib import Path

import numpy as np

from smc_robot.config import Settings
from smc_robot.scoring import FEATURE_NAMES, SetupScorer, feature_vector
from smc_robot.scoring.train import train_model


def test_ml_model_blends_into_score(tmp_path: Path):
    rng = np.random.default_rng(0)
    n = 80
    X = rng.normal(size=(n, len(FEATURE_NAMES)))
    y = (X[:, 0] + X[:, 5] > 0).astype(int)
    y[0] = 0
    y[1] = 1
    path = tmp_path / "smc_scorer.joblib"
    train_model(X, y, path)
    settings = Settings()
    settings.scoring.model_path = str(path)
    settings.scoring.use_ml = True
    settings.scoring.ml_blend = 0.4
    scorer = SetupScorer(settings)
    assert scorer._model is not None
    dummy = {name: 0.0 for name in FEATURE_NAMES}
    dummy["h1_aligned"] = 1.0
    dummy["efficiency"] = 0.4
    dummy["atr_ratio"] = 1.0
    from smc_robot.scoring import rule_score

    rules, _ = rule_score(dummy, settings)
    vector = feature_vector(dummy).reshape(1, -1)
    proba = float(scorer._model.predict_proba(vector)[0][1])
    assert 0.0 <= proba <= 1.0
    assert rules >= 0
