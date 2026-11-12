#!/usr/bin/env python3
import asyncio
import logging
import sys

from src.db.connection import close_db, init_db
from src.logger_config import setup_logging

# Setup root logger first
setup_logging(
    log_dir="logs", log_file="app.log", default_level="INFO", silence_third_party=True
)

# Module-level logger following Python best practices
logger = logging.getLogger(__name__)


async def run_pipeline() -> None:
    """Executes daily scraping and currency update cycle."""
    logger.info("Executing ETL pipeline cycle...")
    # Parsers execution will be orchestrated here
    # Example:
    # await fetch_nbu_rates()
    # await scrape_store_products()
    logger.info("ETL pipeline cycle completed successfully.")


async def main() -> None:
    """Application async entry point."""
    logger.info("Initializing E-gatherer application...")
    try:
        logger.info("Verifying and bootstrapping database schema...")
        await init_db()
        logger.info("Database initialized.")

        # Start the ETL pipeline
        await run_pipeline()

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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user. Exiting.")
        sys.exit(0)
