"""Render the SMC chart-chat overlay for Volatility 75 and Volatility 50 (1s)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from smc_overlay import DIR_BULL, KIND_BOS, KIND_CHOCH, KIND_MSS, analyze, build_setup, chat_lines, pick_dual_pair_trades


def _walk(seed: int, n: int, start: float, vol: float) -> tuple[list[float], list[float], list[float], list[float]]:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0, vol, n)
    # Add a few displacements so BOS / CHoCH / FVG actually print.
    for idx in (40, 90, 140, 175):
        if idx < n:
            rets[idx] *= 6
    close = start * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[close[0]], close[:-1]])
    wick = np.abs(rng.normal(0.0, vol * start * 0.15, n))
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    # Equal highs for EQ SWEEP EXTRA
    if n > 80:
        level = float(high[25])
        high[25] = level
        high[55] = level * 1.0004
        high[70] = level * 1.0020
        close[70] = min(close[70], level * 0.998)
    return open_.tolist(), high.tolist(), low.tolist(), close.tolist()


def _panel(ax, title: str, o, h, l, c):
    x = np.arange(len(c))
    ax.plot(x, c, color="#d8dee9", lw=1.1, zorder=3)
    snap = analyze(o, h, l, c)
    setup = build_setup(o, h, l, c, snap=snap)
    for zone in snap.fvgs[-6:]:
        if zone.mitigated:
            continue
        color = "#2ecc71" if zone.direction == DIR_BULL else "#e74c3c"
        ax.axhspan(zone.low, zone.high, xmin=zone.start_index / len(c), xmax=1.0, color=color, alpha=0.18, zorder=1)
        ax.text(zone.end_index, zone.high, "FVG", color=color, fontsize=8, va="bottom")
    for zone in snap.obs[-5:]:
        if zone.mitigated:
            continue
        color = "#5dade2" if zone.direction == DIR_BULL else "#af7ac5"
        ax.axhspan(zone.low, zone.high, xmin=zone.start_index / len(c), xmax=1.0, color=color, alpha=0.25, zorder=1)
        ax.text(zone.start_index, zone.high, "Order Block", color=color, fontsize=8, va="bottom")
    colors = {KIND_BOS: "#58d68d", KIND_CHOCH: "#f7dc6f", KIND_MSS: "#5dade2"}
    names = {KIND_BOS: "BOS", KIND_CHOCH: "CHoCH", KIND_MSS: "MSS"}
    for event in snap.events[-12:]:
        marker = "^" if event.direction == DIR_BULL else "v"
        ax.scatter(event.index, event.broken, marker=marker, s=40, color=colors[event.kind], zorder=5)
        ax.text(event.index, event.broken, names[event.kind], color=colors[event.kind], fontsize=8)
    for sweep in snap.sweeps[-8:]:
        label = "EQ SWEEP EXTRA" if sweep.equal_extra else "LIQUIDITY SWEEP"
        ax.vlines(sweep.index, sweep.swept_price, sweep.wick, color="#f5b041", lw=2, zorder=4)
        ax.text(sweep.index, sweep.wick, label, color="#f5b041", fontsize=7, rotation=90, va="bottom")
    for pool in snap.equal_pools[-4:]:
        ax.axhline(pool.price, color="#f7dc6f", ls="--", lw=0.8, alpha=0.8)
    ax.set_title(title, color="white")
    ax.set_facecolor("#1b1f2a")
    ax.tick_params(colors="#aeb6bf")
    ax.grid(alpha=0.15, color="#7f8c8d")
    setup_line = f"  SETUP: {'YES ' + ('BULL' if setup.direction == DIR_BULL else 'BEAR') + ' ' + setup.why if setup.valid else 'no (' + setup.why + ')'}"
    return "\n".join(chat_lines(title, snap) + [setup_line]), setup


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/opt/cursor/artifacts/smc_chart_chat_v75_v50.png")
    args = p.parse_args()

    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    fig.patch.set_facecolor("#12151c")
    o, h, l, c = _walk(7, 220, 184500.0, 0.004)
    chat1, setup1 = _panel(axes[0], "Volatility 75 Index", o, h, l, c)
    o, h, l, c = _walk(21, 220, 245000.0, 0.003)
    chat2, setup2 = _panel(axes[1], "Volatility 50 (1s) Index", o, h, l, c)
    _, _, _, pick = pick_dual_pair_trades(setup1, setup2, require_both=True)
    fig.suptitle(
        f"Dual-pair SMC  |  {pick}  |  Liquidity sweep  EQ sweep extra  OB  FVG  BOS  CHoCH  MSS",
        color="white",
        fontsize=13,
    )
    fig.tight_layout()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    chat_path = out.with_name("smc_chart_chat_panel.txt")
    chat_path.write_text(
        "Python ML SMC Bridge  3.03\n"
        "Symbols: Volatility 75 Index  |  Volatility 50 (1s) Index\n"
        f"TRADE: {pick}\n"
        "--------------------------------\n"
        f"{chat1}\n"
        "--------------------------------\n"
        f"{chat2}\n",
        encoding="utf-8",
    )
    print(f"Saved {out}")
    print(f"Saved {chat_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
