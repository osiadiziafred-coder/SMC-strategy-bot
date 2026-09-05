"""Render a demonstration chart of the ML/SMC robot's decisions.

Loads the trained model, evaluates the full pipeline over an offline synthetic
XAUUSD feed and plots price with BUY/SELL command markers plus the ML
probability stream and the confidence threshold.

Usage::

    python scripts/plot_robot_demo.py --seed 123 --start 57861 --window 2500 \
        --out /opt/cursor/artifacts/robot_demo.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ml_smc_robot.config import Config
from ml_smc_robot.features import add_direction_features, build_base_matrix
from ml_smc_robot.ml_model import MLModel
from ml_smc_robot.mt5_connector import SyntheticConnector


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=123)
    p.add_argument("--start", type=int, default=57861)
    p.add_argument("--window", type=int, default=2500)
    p.add_argument("--out", type=str, default="/opt/cursor/artifacts/robot_demo.png")
    args = p.parse_args()

    cfg = Config(data_source="synthetic")
    model = MLModel.load(cfg.model_path)
    conn = SyntheticConnector(cfg, seed=args.seed)
    conn.connect()
    n = len(conn.timeline())
    h1 = conn.get_rates("H1", n)
    m30 = conn.get_rates("M30", n)
    m15 = conn.get_rates("M15", n)

    base = build_base_matrix(h1, m30, m15, cfg)
    p_buy = model.predict_success_proba(add_direction_features(base, 1))
    p_sell = model.predict_success_proba(add_direction_features(base, -1))
    thr = cfg.ml_min_confidence

    b = base
    buy_gate = (
        (b.h1_trend > 0) & (b.m30_trend >= 0)
        & ((b.m15_bos > 0) | (b.m15_choch > 0) | (b.m15_mss > 0) | (b.m15_trend > 0))
        & (b.m15_premium_discount <= 0.85) & (p_buy >= thr)
    ).to_numpy()
    sell_gate = (
        (b.h1_trend < 0) & (b.m30_trend <= 0)
        & ((b.m15_bos < 0) | (b.m15_choch < 0) | (b.m15_mss < 0) | (b.m15_trend < 0))
        & (b.m15_premium_discount >= 0.15) & (p_sell >= thr)
    ).to_numpy()
    # If both fire, keep the higher-probability side (matches brain.decide).
    both = buy_gate & sell_gate
    buy_gate = buy_gate & ~(both & (p_sell > p_buy))
    sell_gate = sell_gate & ~(both & (p_buy >= p_sell))

    s, w = args.start, args.window
    sl = slice(s, s + w)
    close = m15["close"].to_numpy()[sl]
    x = np.arange(w)
    pbw, psw = p_buy[sl], p_sell[sl]
    bg, sg = buy_gate[sl], sell_gate[sl]

    fig, (ax_p, ax_ml) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={"height_ratios": [2, 1]})

    ax_p.plot(x, close, color="#1f77b4", lw=0.9, label=f"{cfg.symbol} M15 close")
    ax_p.scatter(x[bg], close[bg], marker="^", color="#2ca02c", s=70, zorder=5,
                 label=f"BUY command ({int(bg.sum())})")
    ax_p.scatter(x[sg], close[sg], marker="v", color="#d62728", s=70, zorder=5,
                 label=f"SELL command ({int(sg.sum())})")
    ax_p.set_title(f"ML/SMC robot decisions on {cfg.symbol} (offline synthetic feed)")
    ax_p.set_ylabel("Price")
    ax_p.legend(loc="upper left")
    ax_p.grid(alpha=0.2)

    ax_ml.plot(x, pbw, color="#2ca02c", lw=0.8, label="P(BUY success)")
    ax_ml.plot(x, psw, color="#d62728", lw=0.8, label="P(SELL success)")
    ax_ml.axhline(thr, color="black", ls="--", lw=1.0, label=f"ML_MIN_CONFIDENCE = {thr}")
    ax_ml.set_ylim(0, 1)
    ax_ml.set_title("ML setup-success probability")
    ax_ml.set_xlabel("Bar (M15) within demo window")
    ax_ml.set_ylabel("Probability")
    ax_ml.legend(loc="upper left", ncol=3)
    ax_ml.grid(alpha=0.2)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"Saved demo chart -> {out}  (BUY={int(bg.sum())}, SELL={int(sg.sum())})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
