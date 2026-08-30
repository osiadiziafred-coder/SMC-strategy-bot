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
    ob: bool,
    fvg: bool,
    ml_buy: float,
    ml_sell: float,
    decision: str,
) -> str:
    return (
        f"{symbol} | H1={h1_bias} | M30={m30_confirm} | M15={m15_setup} | "
        f"BOS={bos} | MSS={mss} | CHoCH={choch} | Sweep={bool(sweep)} | "
        f"OB={ob} | FVG={fvg} | ML_BUY={ml_buy:.2f} | ML_SELL={ml_sell:.2f} | "
        f"Decision={decision}"
    )


def format_explanation(explain: list[tuple[str, float, float]]) -> str:
    parts = [f"{name}(val={value:.3f}, contrib={contrib:+.3f})" for name, value, contrib in explain]
    return "Explain: " + ", ".join(parts)
