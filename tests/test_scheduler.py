import asyncio
import random
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.main import run_pipeline
from src.scheduler import ScheduleConfig, next_random_run_time, run_scheduled_loop

KYIV = ZoneInfo("Europe/Kyiv")


def test_schedule_config_rejects_invalid_hours() -> None:
    with pytest.raises(ValueError):
        ScheduleConfig(window_start_hour=4, window_end_hour=4)
    with pytest.raises(ValueError):
        ScheduleConfig(window_start_hour=-1, window_end_hour=4)
    with pytest.raises(ValueError):
        ScheduleConfig(window_start_hour=1, window_end_hour=25)


def test_next_random_run_time_before_window_schedules_same_day() -> None:
    config = ScheduleConfig(timezone="Europe/Kyiv", window_start_hour=1, window_end_hour=4)
    now = datetime(2026, 11, 21, 0, 30, tzinfo=KYIV)

    scheduled = next_random_run_time(now, config, rng=random.Random(42))

    assert scheduled.date() == date(2026, 11, 21)
    assert scheduled.tzinfo == KYIV
    assert 1 <= scheduled.hour < 4


def test_next_random_run_time_inside_or_after_window_schedules_next_day() -> None:
    config = ScheduleConfig(timezone="Europe/Kyiv", window_start_hour=1, window_end_hour=4)
    inside = datetime(2026, 11, 21, 2, 15, tzinfo=KYIV)
    after = datetime(2026, 11, 21, 19, 45, tzinfo=KYIV)

    for current in (inside, after):
        scheduled = next_random_run_time(current, config, rng=random.Random(7))
        assert scheduled.date() == date(2026, 11, 22)
        assert 1 <= scheduled.hour < 4


def test_next_random_run_time_handles_kyiv_dst_transitions() -> None:
    config = ScheduleConfig(timezone="Europe/Kyiv", window_start_hour=1, window_end_hour=4)
    spring_forward = datetime(2026, 3, 29, 0, 10, tzinfo=KYIV)
    fall_back = datetime(2026, 10, 25, 0, 10, tzinfo=KYIV)

    for dt in (spring_forward, fall_back):
        for seed in range(25):
            scheduled = next_random_run_time(dt, config, rng=random.Random(seed))
            assert scheduled.date() == dt.date()
            assert 1 <= scheduled.hour < 4


def test_next_random_run_time_produces_varied_times() -> None:
    config = ScheduleConfig(timezone="Europe/Kyiv", window_start_hour=1, window_end_hour=4)
    now = datetime(2026, 11, 21, 12, 0, tzinfo=KYIV)
    samples = {
        next_random_run_time(now, config, rng=random.Random(seed))
        for seed in range(10)
    }
    assert len(samples) > 1


def test_run_scheduled_loop_stops_immediately_when_event_set() -> None:
    stop_event = asyncio.Event()
    stop_event.set()
    calls = 0

    async def job() -> None:
        nonlocal calls
        calls += 1

    asyncio.run(
        run_scheduled_loop(
            job,
            config=ScheduleConfig(),
            stop_event=stop_event,
        )
    )
    assert calls == 0


def test_run_scheduled_loop_executes_job_and_stops_on_signal() -> None:
    stop_event = asyncio.Event()
    calls = 0
    ticks = iter(
        [
            datetime(2026, 11, 21, 0, 50, tzinfo=KYIV),
            datetime(2026, 11, 21, 4, 0, tzinfo=KYIV),
        ]
    )

    async def job() -> None:
        nonlocal calls
        calls += 1
        stop_event.set()

    asyncio.run(
        run_scheduled_loop(
            job,
            config=ScheduleConfig(),
            stop_event=stop_event,
            rng=random.Random(1),
            now_fn=lambda: next(ticks),
        )
    )
    assert calls == 1


class _FailingParser:
    name = "failing_parser"

    async def run(self) -> int:
        raise RuntimeError("boom")


class _SucceedingParser:
    name = "succeeding_parser"

    def __init__(self) -> None:
        self.ran = False

    async def run(self) -> int:
        self.ran = True
        return 3


def test_run_pipeline_isolates_collector_failures() -> None:
    second = _SucceedingParser()
    asyncio.run(run_pipeline(collectors=(_FailingParser(), second)))
    assert second.ran is True
