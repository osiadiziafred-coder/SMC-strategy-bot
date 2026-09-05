import numpy as np

from ml_smc_robot import features as F
from ml_smc_robot.config import Config
from ml_smc_robot.mt5_connector import SyntheticConnector


def _frames(n=3000):
    cfg = Config()
    conn = SyntheticConnector(cfg, n_m15=n, seed=5)
    conn.connect()
    h1 = conn.get_rates("H1", n)
    m30 = conn.get_rates("M30", n)
    m15 = conn.get_rates("M15", n)
    return cfg, h1, m30, m15


def test_base_matrix_has_expected_columns_and_no_nans():
    cfg, h1, m30, m15 = _frames()
    base = F.build_base_matrix(h1, m30, m15, cfg)
    assert list(base.columns) == F.BASE_FEATURES
    assert np.isfinite(base.to_numpy()).all()


def test_direction_features_full_column_set():
    cfg, h1, m30, m15 = _frames()
    base = F.build_base_matrix(h1, m30, m15, cfg)
    buy = F.add_direction_features(base, 1)
    sell = F.add_direction_features(base, -1)
    assert list(buy.columns) == F.FEATURE_COLUMNS
    assert (buy["direction"] == 1).all()
    assert (sell["direction"] == -1).all()
    # pd_dir must flip sign with direction.
    assert np.allclose(buy["pd_dir"], -sell["pd_dir"])


def test_training_dataset_is_time_ordered_and_binary():
    cfg, h1, m30, m15 = _frames()
    cfg.train_bars = 3000
    X, y, ts = F.build_training_dataset(h1, m30, m15, cfg)
    assert len(X) == len(y) == len(ts)
    assert set(np.unique(y)).issubset({0, 1})
    # Timestamps must be non-decreasing (no shuffle / leakage across split).
    t = ts.to_numpy()
    assert (t[1:] >= t[:-1]).all()


def test_live_features_single_row():
    cfg, h1, m30, m15 = _frames()
    _, buy, sell = F.build_live_features(h1, m30, m15, cfg)
    assert len(buy) == 1 and len(sell) == 1
    assert np.isfinite(buy.to_numpy()).all()
