"""Logging helpers producing the detailed, human-readable decision records
required by the spec (bias, confirmation, structure, ML probabilities, decision,
trade parameters and explainability)."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Config


def setup_logger(cfg: Config, name: str = "smc_brain") -> logging.Logger:
    cfg.ensure_dirs()
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    file_handler = logging.FileHandler(Path(cfg.log_dir) / "smc_brain.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def format_decision_line(
    symbol: str,
    h1_bias: str,
    m30_confirm: str,
    m15_setup: str,
    bos: int,
    mss: int,
    choch: int,
    sweep: int,
    eq_sweep: int,
    ob: bool,
    fvg: bool,
    ml_buy: float,
    ml_sell: float,
    decision: str,
) -> str:
    return (
        f"{symbol} | H1={h1_bias} | M30={m30_confirm} | M15={m15_setup} | "
        f"BOS={bos} | MSS={mss} | CHoCH={choch} | Sweep={bool(sweep)} | "
        f"EqSweep={bool(eq_sweep)} | OB={ob} | FVG={fvg} | "
        f"ML_BUY={ml_buy:.2f} | ML_SELL={ml_sell:.2f} | Decision={decision}"
    )


def format_explanation(explain: list[tuple[str, float, float]]) -> str:
    parts = [f"{name}(val={value:.3f}, contrib={contrib:+.3f})" for name, value, contrib in explain]
    return "Explain: " + ", ".join(parts)


def _sign_tag(value: int, pos: str, neg: str) -> str:
    if value > 0:
        return pos
    if value < 0:
        return neg
    return "-"


def _zone_tag(zone) -> str:
    if zone is None:
        return "none"
    return f"{zone.bottom:.2f}-{zone.top:.2f}"


def format_smc_report(symbol: str, states: dict, tick: dict | None = None) -> str:
    """Render a full multi-timeframe SMC readout for the chat/log.

    Brings out, per timeframe: Bias, BOS, MSS, CHoCH, Liquidity sweep,
    Equal-liquidity sweep, Order Block and FVG.
    """

    lines = []
    lines.append("=" * 100)
    title = f"SMC ANALYSIS  |  {symbol}"
    if tick is not None:
        title += f"  |  price={tick.get('bid', float('nan')):.2f}  spread={tick.get('spread_points', 0):.0f}pts"
    lines.append(title)
    lines.append("=" * 100)
    header = (
        f"{'TF':<5} {'Bias':<8} {'BOS':<5} {'CHoCH':<6} {'MSS':<5} "
        f"{'LiqSweep':<10} {'EqLiqSweep':<11} {'OrderBlock':<22} {'FVG':<22}"
    )
    lines.append(header)
    lines.append("-" * 100)
    for tf, s in states.items():
        ob = s.nearest_bull_ob or s.nearest_bear_ob
        fvg = s.nearest_bull_fvg or s.nearest_bear_fvg
        ob_dir = "BULL " if s.nearest_bull_ob else ("BEAR " if s.nearest_bear_ob else "")
        fvg_dir = "BULL " if s.nearest_bull_fvg else ("BEAR " if s.nearest_bear_fvg else "")
        lines.append(
            f"{tf:<5} {s.bias.value:<8} "
            f"{_sign_tag(s.bos, 'UP', 'DOWN'):<5} "
            f"{_sign_tag(s.choch, 'UP', 'DOWN'):<6} "
            f"{_sign_tag(s.mss, 'UP', 'DOWN'):<5} "
            f"{_sign_tag(s.liquidity_sweep, 'BULL', 'BEAR'):<10} "
            f"{_sign_tag(s.equal_liquidity_sweep, 'BULL', 'BEAR'):<11} "
            f"{(ob_dir + _zone_tag(ob)):<22} "
            f"{(fvg_dir + _zone_tag(fvg)):<22}"
        )
    lines.append("=" * 100)
    return "\n".join(lines)
