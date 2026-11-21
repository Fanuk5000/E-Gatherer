import asyncio
import logging
import os
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_SLEEP_CHUNK_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    """Daily randomized scraping window configuration."""

    timezone: str = "Europe/Kyiv"
    window_start_hour: int = 1
    window_end_hour: int = 4

    def __post_init__(self) -> None:
        if not (0 <= self.window_start_hour < self.window_end_hour <= 24):
            raise ValueError(
                "Schedule window must satisfy 0 <= window_start_hour < window_end_hour <= 24."
            )
        ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls) -> ScheduleConfig:
        """Loads schedule window configuration from environment variables."""
        return cls(
            timezone=os.getenv("SCRAPE_TIMEZONE", "Europe/Kyiv"),
            window_start_hour=int(os.getenv("SCRAPE_WINDOW_START_HOUR", "1")),
            window_end_hour=int(os.getenv("SCRAPE_WINDOW_END_HOUR", "4")),
        )


def _window_bounds(
    target_date: date,
    config: ScheduleConfig,
    tz: ZoneInfo,
) -> tuple[datetime, datetime]:
    """Returns localized start and end datetimes for a target calendar date."""
    start_dt = datetime.combine(
        target_date, time(config.window_start_hour, 0), tzinfo=tz
    )
    if config.window_end_hour == 24:
        end_dt = datetime.combine(
            target_date + timedelta(days=1), time(0, 0), tzinfo=tz
        )
    else:
        end_dt = datetime.combine(
            target_date, time(config.window_end_hour, 0), tzinfo=tz
        )
    return start_dt, end_dt


def next_random_run_time(
    now: datetime,
    config: ScheduleConfig,
    rng: random.Random | None = None,
) -> datetime:
    """Picks a random run timestamp within the next eligible daily window."""
    if now.tzinfo is None:
        raise ValueError("'now' must be a timezone-aware datetime.")

    tz = ZoneInfo(config.timezone)
    local_now = now.astimezone(tz)
    today_start, _ = _window_bounds(local_now.date(), config, tz)

    target_date = (
        local_now.date()
        if local_now < today_start
        else local_now.date() + timedelta(days=1)
    )
    window_start, window_end = _window_bounds(target_date, config, tz)

    # Interpolate in UTC so Europe/Kyiv DST jumps never yield non-existent local times.
    start_utc = window_start.astimezone(UTC)
    end_utc = window_end.astimezone(UTC)
    span_seconds = int((end_utc - start_utc).total_seconds())
    offset_seconds = (rng or random).randrange(span_seconds)
    return (start_utc + timedelta(seconds=offset_seconds)).astimezone(tz)


async def _wait_until(
    target: datetime,
    stop_event: asyncio.Event,
    now_fn: Callable[[], datetime],
) -> bool:
    """Sleeps in bounded chunks until target time or stop_event. Returns False if stopped."""
    while not stop_event.is_set():
        remaining = (target - now_fn()).total_seconds()
        if remaining <= 0:
            return True

        chunk = min(remaining, _SLEEP_CHUNK_SECONDS)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=chunk)
            return False
        except TimeoutError:
            continue

    return False


async def run_scheduled_loop(
    job: Callable[[], Awaitable[None]],
    config: ScheduleConfig | None = None,
    stop_event: asyncio.Event | None = None,
    *,
    rng: random.Random | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> None:
    """Executes job once daily at a randomized time inside the configured window."""
    active_config = config or ScheduleConfig.from_env()
    active_stop = stop_event or asyncio.Event()
    tz = ZoneInfo(active_config.timezone)
    clock = now_fn or (lambda: datetime.now(tz))

    while not active_stop.is_set():
        next_run = next_random_run_time(clock(), active_config, rng=rng)
        logger.info(
            "Next scheduled ETL cycle at %s (%s).",
            next_run.isoformat(),
            active_config.timezone,
        )
        should_run = await _wait_until(next_run, active_stop, clock)
        if not should_run:
            break

        logger.info("Starting scheduled ETL cycle...")
        try:
            await job()
        except Exception:
            logger.exception("Scheduled ETL cycle failed unexpectedly.")

    logger.info("Scheduler loop stopped.")
