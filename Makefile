.DEFAULT_GOAL := help

OS_ID := $(shell . /etc/os-release 2>/dev/null && echo "$$ID" || uname -s)
OS_LIKE := $(shell . /etc/os-release 2>/dev/null && echo "$$ID_LIKE" || true)

.PHONY: help setup setup-deps currency scrape scrape-save bench bench-large run run-once test test-verbose

help:
	@echo "Detected OS: $(OS_ID)"
	@echo "Targets:"
	@echo "  make setup        Sync uv deps and install Playwright Firefox binary"
	@echo "  make setup-deps   Sync uv deps and install OS libs + Firefox (Ubuntu/Fedora)"
	@echo "  make currency     Run NBU currency API collector"
	@echo "  make scrape       Dry-run webscraper.io Playwright Gecko scraper"
	@echo "  make scrape-save  Run webscraper.io scraper and save to PostgreSQL"
	@echo "  make bench        Compare bare SQL vs pg_trgm queries and views"
	@echo "  make bench-large  Compare bare SQL vs pg_trgm GIN on 100k synthetic rows"
	@echo "  make run          Start daily randomized (01:00-04:00 Kyiv) ETL scheduler"
	@echo "  make run-once     Run full ETL pipeline once and exit"
	@echo "  make test         Run unit test suite with pytest"
	@echo "  make test-verbose Run unit test suite with verbose output"

setup:
	uv sync
	uv run playwright install firefox

setup-deps:
	uv sync
	@case " $(OS_ID) $(OS_LIKE) " in \
		*" ubuntu "*|*" debian "*) \
			echo "Installing Playwright Firefox + apt system deps ($(OS_ID))..."; \
			sudo apt-get update && uv run playwright install --with-deps firefox ;; \
		*" fedora "*|*" rhel "*|*" centos "*) \
			echo "Installing Playwright Firefox + dnf system deps ($(OS_ID))..."; \
			sudo dnf install gtk3 dbus-glib libXt alsa-lib nss xorg-x11-server-Xvfb && uv run playwright install firefox ;; \
		*) \
			echo "Unsupported distro '$(OS_ID)' for auto system deps; installing Firefox binary only."; \
			uv run playwright install firefox ;; \
	esac

currency:
	uv run python -m src.collectors.api.currency

scrape:
	uv run python -m src.collectors.websites.webscraper_io

scrape-save:
	uv run python -m src.collectors.websites.webscraper_io --save

bench:
	uv run python -m scripts.benchmark_trgm

bench-large:
	uv run python -m scripts.benchmark_trgm_large

run:
	uv run python -m src.main

run-once:
	uv run python -m src.main --once

test:
	uv run python -m pytest

test-verbose:
	uv run python -m pytest -v
