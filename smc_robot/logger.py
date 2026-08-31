"""Project logger used by the live loop and CLI."""

from __future__ import annotations

from pathlib import Path
import logging


def configure_logging(log_dir: str) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(Path(log_dir) / "smc_robot.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
