import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    default_level: str = "INFO",
    log_dir: str = "logs",
    log_file: str = "app.log",
    silence_third_party: bool = True,
) -> None:
    """Configures root logger with console and rotating file handlers."""
    log_level = os.getenv("LOG_LEVEL", default_level).upper()

    # Ensure log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_path = log_path / log_file

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S",
    )

    # Console Handler (stdout for Docker logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Rotating File Handler (5MB max size, 3 backup files to protect HDD)
    file_handler = RotatingFileHandler(
        filename=file_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Prevent duplicate handlers on re-runs
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    if silence_third_party:
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("playwright").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
