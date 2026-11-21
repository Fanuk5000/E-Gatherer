#!/usr/bin/env python3
import argparse
import asyncio
import logging
import signal
import sys
from collections.abc import Sequence
from typing import Protocol

from src.collectors.api.currency import NbuCurrencyParser
from src.collectors.websites.webscraper_io import WebScraperLoadMoreScraper
from src.db.connection import close_db, init_db
from src.logger_config import setup_logging
from src.scheduler import run_scheduled_loop

# Setup root logger first
setup_logging(
    log_dir="logs", log_file="app.log", default_level="INFO", silence_third_party=True
)

# Module-level logger following Python best practices
logger = logging.getLogger(__name__)


class RunnableParser(Protocol):
    """Structural contract for ETL collectors orchestrated by run_pipeline."""

    @property
    def name(self) -> str: ...

    async def run(self) -> int: ...


async def run_pipeline(
    collectors: Sequence[RunnableParser] | None = None,
) -> None:
    """Executes daily scraping and currency update cycle sequentially."""
    logger.info("Executing ETL pipeline cycle...")
    # Currency runs first so website scrapers resolve the freshest USD/UAH rate.
    active_collectors: Sequence[RunnableParser] = (
        collectors
        if collectors is not None
        else (
            NbuCurrencyParser(),
            WebScraperLoadMoreScraper(),
        )
    )
    for parser in active_collectors:
        try:
            await parser.run()
        except Exception:
            logger.exception("Collector '%s' failed; continuing pipeline.", parser.name)

    logger.info("ETL pipeline cycle completed.")


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Registers SIGINT/SIGTERM handlers for graceful scheduler shutdown."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            continue


async def main(run_once: bool = False) -> None:
    """Application async entry point."""
    logger.info("Initializing E-gatherer application...")
    try:
        logger.info("Verifying and bootstrapping database schema...")
        await init_db()
        logger.info("Database initialized.")

        if run_once:
            await run_pipeline()
        else:
            stop_event = asyncio.Event()
            _install_signal_handlers(stop_event)
            await run_scheduled_loop(run_pipeline, stop_event=stop_event)

    except Exception:
        logger.exception(
            "Fatal error during execution:",
        )
        sys.exit(1)
    finally:
        logger.info("Shutting down database connection pool...")
        await close_db()
        logger.info("E-gatherer shut down cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E-gatherer ETL runner.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single ETL pipeline cycle immediately and exit.",
    )
    cli_args = parser.parse_args()
    try:
        asyncio.run(main(run_once=cli_args.once))
    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user. Exiting.")
        sys.exit(0)
