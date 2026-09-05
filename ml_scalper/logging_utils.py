"""Human-readable decision logs for the ML scalper (no SMC tags)."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Config


def setup_logger(cfg: Config, name: str = "ml_scalper") -> logging.Logger:
    cfg.ensure_dirs()
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    file_handler = logging.FileHandler(Path(cfg.log_dir) / "ml_scalper.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def format_decision_line(
    symbol: str,
    m15_regime: str,
    m5_setup: str,
    ml_buy: float,
    ml_sell: float,
    ml_none: float,
    p_tp_buy: float,
    p_tp_sell: float,
    decision: str,
) -> str:
    return (
        f"{symbol} | M15={m15_regime} | M5={m5_setup} | "
        f"P(BUY)={ml_buy:.2f} P(SELL)={ml_sell:.2f} P(NO-TRADE)={ml_none:.2f} | "
        f"E[TP|BUY]={p_tp_buy:.2f} E[TP|SELL]={p_tp_sell:.2f} | Decision={decision}"
    )


def format_explanation(explain: list[tuple[str, float, float]]) -> str:
    parts = [f"{name}(val={value:.3f}, contrib={contrib:+.3f})" for name, value, contrib in explain]
    return "Explain: " + ", ".join(parts)


def format_regime_report(symbol: str, flags: dict, tick: dict | None, score) -> str:
    lines = [
        "=" * 88,
        f"ML SCALPER ANALYSIS  |  {symbol}",
    ]
    if tick is not None:
        lines[1] += f"  |  bid={tick.get('bid', float('nan')):.2f}  spread={tick.get('spread_points', 0):.0f}pts"
    lines.append("=" * 88)
    lines.append(
        f"M15 regime     : {'BULLISH' if flags.get('m15_bull') else ('BEARISH' if flags.get('m15_bear') else 'FLAT')}"
    )
    lines.append(
        f"M5 pullback    : buy={flags.get('pullback_buy')}  sell={flags.get('pullback_sell')}  near_EMA/VWAP={flags.get('near_ma')}"
    )
    lines.append(
        f"M5 momentum    : up={flags.get('momentum_up')}  down={flags.get('momentum_down')}"
    )
    lines.append(f"Setup          : BUY={flags.get('buy_setup')}  SELL={flags.get('sell_setup')}")
    if score is not None:
        lines.append(
            f"ML direction   : BUY {score.p_buy:.1%}  SELL {score.p_sell:.1%}  NO-TRADE {score.p_none:.1%}"
        )
        lines.append(
            f"Expected TP    : BUY {score.p_tp_buy:.1%}  SELL {score.p_tp_sell:.1%}"
        )
    lines.append("=" * 88)
    return "\n".join(lines)
