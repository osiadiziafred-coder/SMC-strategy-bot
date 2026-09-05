from pathlib import Path

import numpy as np

from ml_scalper import features as F
from ml_scalper.config import Config
from ml_scalper.mt5_connector import SyntheticConnector

SMC_TOKENS = ("bos", "choch", "mss", "fvg", "order_block", "liquidity_sweep", "ob_distance")


def _frames(symbol="Volatility 75 Index", n_m1=8000):
    cfg = Config.for_symbol(symbol, data_source="synthetic", train_bars=1200, live_bars=300)
    conn = SyntheticConnector(cfg, n_m1=n_m1, seed=5)
    conn.connect()
    return cfg, conn.get_rates("M15", 800), conn.get_rates("M5", 1200), conn.get_rates("M1", 2000)


def test_base_matrix_columns_have_no_nans_and_no_smc():
    cfg, m15, m5, m1 = _frames()
    base = F.build_base_matrix(m15, m5, m1, cfg)
    assert list(base.columns) == F.BASE_FEATURES
    assert np.isfinite(base.to_numpy()).all()
    joined = " ".join(base.columns).lower()
    for tok in SMC_TOKENS:
        assert tok not in joined


def test_direction_features_flip_with_side():
    cfg, m15, m5, m1 = _frames()
    base = F.build_base_matrix(m15, m5, m1, cfg)
    buy = F.add_direction_features(base, 1)
    sell = F.add_direction_features(base, -1)
    assert list(buy.columns) == F.FEATURE_COLUMNS
    assert (buy["direction"] == 1).all()
    assert (sell["direction"] == -1).all()
    assert np.allclose(buy["regime_align"], -sell["regime_align"])


def test_training_dataset_time_ordered():
    cfg, m15, m5, m1 = _frames()
    data = F.build_training_dataset(m15, m5, m1, cfg)
    assert set(np.unique(data["y_dir"])).issubset({0, 1, 2})
    assert set(np.unique(data["y_out"])).issubset({0, 1})
    t = data["ts_out"].to_numpy()
    assert (t[1:] >= t[:-1]).all()
    assert data["y_dir"].nunique() >= 2
    assert len(data["X_out"]) > 200


def test_live_features_single_row():
    cfg, m15, m5, m1 = _frames()
    last, buy, sell = F.build_live_features(m15, m5, m1, cfg)
    assert len(last) == 1 and len(buy) == 1 and len(sell) == 1
    assert np.isfinite(buy.to_numpy()).all()


def test_package_source_has_no_smc_concepts():
    root = Path(__file__).resolve().parents[1] / "ml_scalper"
    banned = ("order block", "fair value gap", "liquidity sweep", "change of character", "break of structure")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in banned:
            assert token not in text, f"{path} contains {token!r}"
