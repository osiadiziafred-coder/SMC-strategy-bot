"""Plot a demo of the ML scalper filters on synthetic M5 data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml_scalper.config import Config
from ml_scalper.features import live_setup_flags, build_base_matrix
from ml_scalper.mt5_connector import SyntheticConnector
from ml_scalper import indicators as ind


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="Volatility 75 Index")
    p.add_argument("--out", default="ml_scalper_demo.png")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args(argv)

    cfg = Config.for_symbol(args.symbol, data_source="synthetic", live_bars=400, train_bars=2500)
    conn = SyntheticConnector(cfg, seed=args.seed, n_m1=12_000)
    conn.connect()
    m15 = conn.get_rates("M15", 400)
    m5 = conn.get_rates("M5", 400)
    m1 = conn.get_rates("M1", 400)
    base = build_base_matrix(m15, m5, m1, cfg)
    ema20 = ind.ema(m5["close"], 20)
    ema50 = ind.ema(m5["close"], 50)
    vwap = ind.rolling_vwap(m5, cfg.vwap_window)

    buy_x, buy_y, sell_x, sell_y = [], [], [], []
    for i in range(80, len(base)):
        flags = live_setup_flags(base.iloc[i], cfg)
        ts = base.index[i]
        px = float(m5["close"].iloc[i])
        if flags["buy_setup"]:
            buy_x.append(ts)
            buy_y.append(px)
        if flags["sell_setup"]:
            sell_x.append(ts)
            sell_y.append(px)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(m5.index, m5["close"], color="#222", linewidth=1.0, label="M5 close")
    ax.plot(m5.index, ema20, color="#1f77b4", linewidth=1.0, label="EMA 20")
    ax.plot(m5.index, ema50, color="#ff7f0e", linewidth=1.0, label="EMA 50")
    ax.plot(m5.index, vwap, color="#2ca02c", linewidth=1.0, linestyle="--", label="VWAP")
    ax.scatter(buy_x, buy_y, color="#2ca02c", marker="^", s=36, label="BUY setup", zorder=5)
    ax.scatter(sell_x, sell_y, color="#d62728", marker="v", s=36, label="SELL setup", zorder=5)
    ax.set_title(f"ML scalper filters (no SMC) — {cfg.symbol}")
    ax.set_ylabel("Price")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    out = Path(args.out)
    fig.savefig(out, dpi=120)
    print(f"Wrote {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
