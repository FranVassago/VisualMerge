from __future__ import annotations

import logging
from pathlib import Path


LOG_PATH = Path(__file__).resolve().parent.parent / "simulator.log"


def build_logger() -> logging.Logger:
    logger = logging.getLogger("warehouse_sim")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
