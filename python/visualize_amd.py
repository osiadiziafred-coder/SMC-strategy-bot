"""Render a textbook AMD cycle so the session model is visually inspectable."""

from __future__ import annotations

import os
import sys
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "python"))

from amd_engine import (  # noqa: E402
    AMDConfig,
    AMDEngine,
    Direction,
    Phase,
    build_range,
    synthesize_amd_sell_day,
)


def _candles(ax, candles):
    width = 0.6
    for i, c in enumerate(candles):
        color = "#26a69a" if c.close >= c.open else "#ef5350"
        ax.vlines(i, c.low, c.high, color=color, linewidth=1.0)
        body_low = min(c.open, c.close)
        body_h = max(abs(c.close - c.open), 0.00002)
        ax.add_patch(
            Rectangle((i - width / 2, body_low), width, body_h, facecolor=color, edgecolor=color)
        )


def render(output_path: str) -> str:
    day = datetime(2026, 3, 10, 0, 0, 0)
    candles = synthesize_amd_sell_day(day)
    cfg = AMDConfig(require_rejection=False, min_sl_points=0, max_sl_points=20000)
    engine = AMDEngine(cfg)
    signal = None
    for i, bar in enumerate(candles):
        sig = engine.process_bar(bar, candles[:i])
        if sig is not None and signal is None:
            signal = (i, sig)

    rng = build_range(candles, day.replace(hour=8), cfg)
    asia_end_idx = max(i for i, c in enumerate(candles) if c.time.hour < 8)

    fig, ax = plt.subplots(figsize=(14, 7), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")
    _candles(ax, candles)

    ax.axvspan(-0.5, asia_end_idx + 0.5, color="#1f6feb", alpha=0.12, label="Accumulation (Asia)")
    ax.axhline(rng.high, color="#3fb950", linestyle="--", linewidth=1.2, label="Buy-side liquidity (Asia high)")
    ax.axhline(rng.low, color="#f85149", linestyle="--", linewidth=1.2, label="Sell-side liquidity (Asia low)")

    if engine.sweep.active and engine.sweep.t_sweep is not None:
        sweep_idx = next(i for i, c in enumerate(candles) if c.time == engine.sweep.t_sweep)
        ax.annotate(
            "MANIPULATION\nliquidity sweep",
            xy=(sweep_idx, engine.sweep.extreme),
            xytext=(sweep_idx - 18, engine.sweep.extreme + 0.0008),
            color="#ffa657",
            fontsize=9,
            arrowprops=dict(arrowstyle="->", color="#ffa657"),
        )
        ax.add_patch(
            Rectangle(
                (sweep_idx - 0.5, rng.high),
                3.5,
                engine.sweep.extreme - rng.high,
                facecolor="#d29922",
                alpha=0.35,
                edgecolor="#ffa657",
            )
        )

    if signal is not None:
        idx, sig = signal
        ax.scatter([idx], [sig.entry], marker="v", s=120, color="#ff7b72", zorder=5, label="SELL entry")
        ax.axhline(sig.sl, color="#ff7b72", linestyle=":", linewidth=1.0, label="Stop loss")
        ax.axhline(sig.tp, color="#e3b341", linestyle=":", linewidth=1.0, label="Take profit")
        ax.annotate(
            "DISTRIBUTION entry",
            xy=(idx, sig.entry),
            xytext=(idx + 6, sig.entry + 0.0006),
            color="#ff7b72",
            fontsize=9,
            arrowprops=dict(arrowstyle="->", color="#ff7b72"),
        )
        if engine.mss.confirmed:
            mss_idx = next(i for i, c in enumerate(candles) if c.time == engine.mss.t_shift)
            ax.annotate(
                "MSS / BOS",
                xy=(mss_idx, engine.mss.broken_level),
                xytext=(mss_idx - 8, engine.mss.broken_level - 0.0008),
                color="#d2a8ff",
                fontsize=9,
                arrowprops=dict(arrowstyle="->", color="#d2a8ff"),
            )

    ax.set_title(
        "AMD Session Model  —  Accumulation → Manipulation → Distribution",
        color="white",
        fontsize=14,
        pad=12,
    )
    ax.set_xlabel("M5 bars (server time from 00:00)", color="#8b949e")
    ax.set_ylabel("Price", color="#8b949e")
    ax.tick_params(colors="#8b949e")
    for spine in ax.spines.values():
        spine.set_color("#30363d")
    legend = ax.legend(loc="upper right", facecolor="#161b22", edgecolor="#30363d", fontsize=8)
    for text in legend.get_texts():
        text.set_color("#c9d1d9")
    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


if __name__ == "__main__":
    out = os.path.join(ROOT, "docs", "amd_cycle_example.png")
    print(render(out))
