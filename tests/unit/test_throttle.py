"""Тесты троттлинга: token-bucket на процесс (виртуальное время)."""

from __future__ import annotations

from typing import Any

import pytest

from ati_hh_mcp.config import Config
from ati_hh_mcp.hh.client import HHClient, TokenBucket, get_rate_limiter

from ..conftest import MockHH, make_config


class VirtualClock:
    """Часы на вручную продвигаемом виртуальном времени."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class VirtualSleep:
    """asyncio.sleep без реального ожидания: продвигает виртуальные часы."""

    def __init__(self, clock: VirtualClock) -> None:
        self.clock = clock
        self.pauses: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.pauses.append(seconds)
        self.clock.advance(seconds)


def _bucket(rate: int) -> tuple[TokenBucket, VirtualClock, VirtualSleep]:
    clock = VirtualClock()
    sleep = VirtualSleep(clock)
    return TokenBucket(rate, clock=clock, sleep=sleep), clock, sleep


def test_bucket_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError, match="положительным"):
        TokenBucket(0)


async def test_burst_up_to_capacity_without_waiting() -> None:
    bucket, _clock, sleep = _bucket(25)
    for _ in range(25):
        await bucket.acquire()
    assert sleep.pauses == []


async def test_excess_requests_wait_for_refill() -> None:
    bucket, _clock, sleep = _bucket(25)
    for _ in range(30):
        await bucket.acquire()
    # 25 запросов мгновенно; каждый сверх – ждёт ~60/25 = 2.4 с пополнения
    # (пауза = 2.4 с плюс до 1 мс запаса против флоат-дедлока).
    assert len(sleep.pauses) == 5
    assert all(2.4 - 1e-9 <= p <= 2.401 + 1e-9 for p in sleep.pauses)
    assert sum(sleep.pauses) >= 5 * 2.4 - 1e-9


async def test_bucket_refills_after_idle() -> None:
    bucket, clock, sleep = _bucket(25)
    for _ in range(25):
        await bucket.acquire()
    clock.advance(60.0)  # минута простоя – ведро полное снова.
    await bucket.acquire()
    assert sleep.pauses == []


async def test_batch_respects_rate_over_time() -> None:
    """Пачка из 50 запросов при лимите 25/мин занимает >= минуты."""
    bucket, _clock, sleep = _bucket(25)
    for _ in range(50):
        await bucket.acquire()
    assert sum(sleep.pauses) + 1e-9 >= 25 * (60.0 / 25)  # 25 ожиданий по 2.4 с.


async def test_client_throttles_requests(mock_hh: MockHH) -> None:
    """Клиент с ведром 25/мин: пачка из 40 запросов проходит, но с ожиданием."""
    mock_hh.json_response = {"items": []}
    bucket, _clock, sleep = _bucket(25)
    config = make_config(rate_limit=25)
    async with HHClient(config, transport=mock_hh.transport, rate_limiter=bucket) as client:
        for _ in range(40):
            await client.get("/vacancies", params={"page": 0, "per_page": 1})
    assert len(mock_hh.requests) == 40
    assert len(sleep.pauses) == 15  # всё сверх ёмкости – с ожиданием.
    assert sum(sleep.pauses) + 1e-9 >= 15 * 2.4  # не быстрее лимита.


def test_global_limiter_shared_and_recreated_on_rate_change() -> None:
    first = get_rate_limiter(25)
    assert get_rate_limiter(25) is first  # одно ведро на процесс.
    other = get_rate_limiter(50)
    assert other is not first
    assert other.rate_per_minute == 50
    assert get_rate_limiter(50) is other


def test_config_rate_limit_default_and_env() -> None:
    assert make_config().rate_limit == 25

    def cfg(env: dict[str, str]) -> Config:
        return Config.from_env(env)

    assert cfg({"HH_RATE_LIMIT": "120"}).rate_limit == 120
    # Некорректное и неположительное значения откатываются к дефолту.
    assert cfg({"HH_RATE_LIMIT": "много"}).rate_limit == 25
    assert cfg({"HH_RATE_LIMIT": "0"}).rate_limit == 25
    assert cfg({"HH_RATE_LIMIT": "-5"}).rate_limit == 25


async def test_client_uses_global_limiter_from_config(mock_hh: MockHH) -> None:
    """Без явного rate_limiter клиент берёт процессное ведро по конфигу."""
    config = make_config(rate_limit=100)
    async with HHClient(config, transport=mock_hh.transport) as client:
        await client.get("/dictionaries")
    bucket = get_rate_limiter(100)
    assert bucket.capacity == 100
    # Один токен израсходован: осталось меньше полной ёмкости.
    assert bucket._tokens < 100  # noqa: SLF001 - проверка внутреннего состояния в тесте


def test_make_config_accepts_rate_limit_override() -> None:
    config: Any = make_config(rate_limit=7)
    assert config.rate_limit == 7
