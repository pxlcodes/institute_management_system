"""Rotating application logging and process exception hooks."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from elh.config import AppConfig


def configure_logging(config: AppConfig) -> Path:
    config.log_directory.mkdir(parents=True, exist_ok=True)
    log_path = config.log_directory / "elh-management.log"
    root = logging.getLogger()
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    root.setLevel(level)

    existing = next(
        (
            handler
            for handler in root.handlers
            if getattr(handler, "_elh_log_path", None) == str(log_path.resolve())
        ),
        None,
    )
    if existing is None:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=max(100_000, config.log_max_bytes),
            backupCount=max(1, config.log_backup_count),
            encoding="utf-8",
        )
        handler._elh_log_path = str(log_path.resolve())  # type: ignore[attr-defined]
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"
            )
        )
        root.addHandler(handler)
    return log_path


def install_exception_hooks() -> None:
    logger = logging.getLogger("elh.unhandled")

    def process_hook(exception_type, exception, traceback) -> None:
        if issubclass(exception_type, KeyboardInterrupt):
            sys.__excepthook__(exception_type, exception, traceback)
            return
        logger.critical("Unhandled process exception", exc_info=(exception_type, exception, traceback))

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        logger.critical(
            "Unhandled thread exception",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = process_hook
    threading.excepthook = thread_hook
