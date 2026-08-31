"""Render SMC detections on the synthetic XAUUSD-style buy setup."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from smc_robot.config import load_config
from smc_robot.models import Direction
from smc_robot.smc.analyze import analyze_timeframe
from tests.factories import m15_buy_setup


def plot_smc(path: Path) -> Path:
    candles = m15_buy_setup()
    analysis = analyze_timeframe(candles, load_config())
    window = candles[-48:]
    offset = len(candles) - len(window)

    fig, ax = plt.subplots(figsize=(14, 7))
    for i, candle in enumerate(window):
        color = "#2e8b57" if candle.close >= candle.open else "#c0392b"
        ax.vlines(i, candle.low, candle.high, color=color, linewidth=1)
        body_low = min(candle.open, candle.close)
        body_high = max(candle.open, candle.close)
        ax.add_patch(
            Rectangle((i - 0.3, body_low), 0.6, max(body_high - body_low, 0.05), color=color, alpha=0.9)
        )

    for gap in analysis.fvgs:
        x = gap.index - offset
        if 0 <= x < len(window):
            ax.axhspan(gap.low, gap.high, color="#f1c40f", alpha=0.18, zorder=0)
    for block in analysis.order_blocks:
        x = block.index - offset
        if 0 <= x < len(window):
            ax.axhspan(block.low, block.high, color="#3498db", alpha=0.18, zorder=0)
    for sweep in analysis.sweeps[-3:]:
        x = sweep.index - offset
        if 0 <= x < len(window):
            ax.scatter([x], [sweep.wick], marker="v" if sweep.direction == Direction.BUY else "^", color="#8e44ad", s=60, zorder=5)
    for event in analysis.events[-8:]:
        x = event.index - offset
        if 0 <= x < len(window):
            ax.annotate(event.event_type.value, (x, event.close), fontsize=8, color="#2c3e50")

    ax.set_title(f"SMC detections on synthetic XAUUSDm M15  |  trend={analysis.trend.value}")
    ax.set_xlabel("Bar")
    ax.set_ylabel("Price")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


if __name__ == "__main__":
    out = Path("artifacts/smc_m15_detections.png")
    plot_smc(out)
    print(out)
