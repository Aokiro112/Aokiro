"""
Architect-JS Core Engine — Structured Logger
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(name: str = "architect_js", log_file: Optional[str] = None, level: str = "INFO") -> logging.Logger:
    """
    Configure and return a logger with both console (rich) and file handlers.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console handler (minimal format for rich-rendered output)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_fmt = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        file_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "architect_js") -> logging.Logger:
    """Get logger by name (configures if not already set up)."""
    from .config import get_config
    cfg = get_config()
    return setup_logger(name, cfg.log.log_file, cfg.log.level)
