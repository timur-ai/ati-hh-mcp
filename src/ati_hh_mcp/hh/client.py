"""HTTP-клиент к API hh.ru: заголовки, таймауты, троттлинг, повторы.

Троттлинг – token-bucket на процесс (``HH_RATE_LIMIT`` запросов в минуту).
Автоматические повторы – только для GET при ответе 429: до трёх повторных
попыток с учётом заголовка ``Retry-After`` либо экспоненциального backoff
0.5/1/2 секунды. Мутации (POST/PUT/DELETE) не повторяются никогда: обрыв
сети мог произойти после применения операции на стороне hh.ru.

Тела запросов: ``json=`` (основной путь), ``data=`` (form-encoded) и
``files=``/``post_multipart`` (multipart/form-data) – для операций hh.ru,
требующих form-тело (отклик на вакансию, OAuth-обмен).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .. import __version__
from ..config import Config
from .errors import HHError, error_from_response

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0

# Повторы GET при 429: паузы между попытками (секунды), до трёх повторов.
GET_RETRY_BACKOFFS: tuple[float, ...] = (0.5, 1.0, 2.0)

# Подсказка для мутаций, завершившихся обрывом: операция могла примениться.
MAYBE_APPLIED_HINT = (
    "Операция могла не выполниться – проверьте результат перед повтором"
)

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class HHAuthExpiredError(HHError):
    """Ответ 401: токен hh.ru отсутствует, недействителен или истёк.

    Подтип HHError с флагом ``auth_expired=True``; OAuth-слой (M5)
    строит авто-refresh именно на этом подтипе.
    """

    auth_expired: bool = True


def user_agent(ua_email: str) -> str:
    """User-Agent по требованию hh.ru: приложение/версия и контактный email."""
    return f"ati-hh-mcp/{__version__} ({ua_email})"


class TokenBucket:
    """Token-bucket для троттлинга запросов (на процесс).

    Ведро вмещает ``rate_per_minute`` токенов и пополняется со скоростью
    ``rate_per_minute / 60`` токенов в секунду; каждый запрос расходует один
    токен. При пустом ведре запрос ждёт пополнения (в порядке поступления,
    но без строгой очереди – проснувшиеся конкурируют за токен).

    ``clock``/``sleep`` внедряются тестами для виртуального времени.
    """

    def __init__(
        self,
        rate_per_minute: int,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute должен быть положительным")
        self.rate_per_minute = rate_per_minute
        self.capacity = float(rate_per_minute)
        self._refill_rate = rate_per_minute / 60.0
        self._tokens = float(rate_per_minute)
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_refill = clock()

    def _refill(self, now: float) -> None:
        """Доливает токены по времени, прошедшему с прошлого пополнения."""
        elapsed = max(0.0, now - self._last_refill)
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self._refill_rate)
            self._last_refill = now

    async def acquire(self) -> None:
        """Ждёт доступный токен (при приближении к лимиту – ожидание)."""
        while True:
            async with self._lock:
                now = self._clock()
                self._refill(now)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # Сколько ждать до следующего целого токена; +1 мс запаса
                # исключает флоат-дедлок (ожидание ровно на грани округления).
                wait_for = (1.0 - self._tokens) / self._refill_rate + 1e-3
            await self._sleep(wait_for)


# Ведро троттлинга общее на процесс (лимит hh.ru действует на клиента целиком).
_global_bucket: TokenBucket | None = None


def get_rate_limiter(rate_per_minute: int) -> TokenBucket:
    """Возвращает процессное ведро, при смене лимита – пересоздаёт."""
    global _global_bucket
    if _global_bucket is None or _global_bucket.rate_per_minute != rate_per_minute:
        _global_bucket = TokenBucket(rate_per_minute)
    return _global_bucket


def reset_rate_limiter() -> None:
    """Сбрасывает процессное ведро (тесты)."""
    global _global_bucket
    _global_bucket = None


def _retry_after_seconds(response: httpx.Response, fallback: float) -> float:
    """Пауза из Retry-After (секунды); при отсутствии/мусоре – fallback."""
    raw = response.headers.get("Retry-After")
    if raw is not None:
        try:
            value = float(raw.strip())
            if value >= 0:
                return value
        except ValueError:
            pass  # HTTP-date и прочие форматы не поддерживаем – fallback.
    return fallback


class HHClient:
    """Тонкая обёртка над httpx.AsyncClient для API hh.ru."""

    def __init__(
        self,
        config: Config,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        rate_limiter: TokenBucket | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        """``rate_limiter``/``sleep`` внедряются тестами; по умолчанию –
        процессное ведро по config.rate_limit и настоящий asyncio.sleep."""
        headers = {
            "User-Agent": user_agent(config.ua_email),
            "Accept": "application/json",
        }
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        self._client = httpx.AsyncClient(
            base_url=config.api_base,
            headers=headers,
            timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            transport=transport,
        )
        self._rate_limiter = rate_limiter if rate_limiter is not None else get_rate_limiter(
            config.rate_limit
        )
        self._sleep = sleep

    @property
    def base_url(self) -> str:
        """Базовый URL API (для тестов и диагностики)."""
        return str(self._client.base_url)

    async def _request_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Один HTTP-вызов (без троттлинга и повторов).

        ``data`` – form-encoded тело, ``files`` – multipart-тело
        (значения вида ``{field: (None, value)}`` для текстовых полей);
        ``json`` – JSON-тело (существующий путь не изменился).
        """
        return await self._client.request(
            method, path, params=params, json=json, data=data, files=files
        )

    def _transport_error(self, method: str, exc: Exception) -> HHError:
        """Преобразует сетевые сбои httpx в структурированные HHError.

        GET безопасно повторять вручную; для мутаций повтор небезопасен –
        операция могла примениться на стороне hh.ru.
        """
        retryable = method == "GET"
        if isinstance(exc, httpx.TimeoutException):
            return HHError(
                "timeout",
                "hh.ru не ответил вовремя: истёк таймаут запроса.",
                retryable=retryable,
                hint=None if retryable else MAYBE_APPLIED_HINT,
            )
        return HHError(
            "network_error",
            f"Сетевая ошибка обращения к hh.ru: {exc.__class__.__name__}.",
            retryable=retryable,
            hint=None if retryable else MAYBE_APPLIED_HINT,
        )

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Единая точка запроса: троттлинг, повторы (GET + 429), ошибки.

        Возвращает сырой ответ со статусом < 400; статусы >= 400
        превращаются в HHError (401 – в HHAuthExpiredError).
        """
        attempt_backoffs = GET_RETRY_BACKOFFS if method == "GET" else ()
        retries_left = len(attempt_backoffs)
        while True:
            await self._rate_limiter.acquire()
            try:
                response = await self._request_once(
                    method, path, params=params, json=json, data=data, files=files
                )
            except httpx.TransportError as exc:
                # Никаких автоповторов даже для GET (только статус 429).
                raise self._transport_error(method, exc) from exc

            if response.status_code == 429 and retries_left > 0:
                pause = _retry_after_seconds(
                    response, attempt_backoffs[len(attempt_backoffs) - retries_left]
                )
                retries_left -= 1
                await self._sleep(pause)
                continue

            if response.status_code >= 400:
                try:
                    body: Any = response.json()
                except ValueError:
                    body = None
                if response.status_code == 401:
                    base = error_from_response(401, body)
                    raise HHAuthExpiredError(
                        base.code,
                        base.description,
                        retryable=base.retryable,
                        hint=base.hint,
                    ) from None
                raise error_from_response(response.status_code, body) from None
            return response

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        """Запрос с разбором JSON-ответа.

        Ответ возвращается как есть: параметры пагинации (page/per_page)
        передаются вызывающим кодом, служебные поля (found/pages/clusters)
        проходят насквозь без фильтрации.
        """
        response = await self._send(
            method, path, params=params, json=json, data=data, files=files
        )
        if not response.content:
            return None
        return response.json()

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """GET-запрос к API hh.ru (единственный метод с автоповтором 429)."""
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        """POST-запрос к API hh.ru (без автоповторов).

        ``data``/``files`` – form-encoded/multipart-тело вместо JSON.
        """
        return await self._request("POST", path, params=params, json=json, data=data, files=files)

    async def post_multipart(self, path: str, *, fields: dict[str, str]) -> httpx.Response:
        """POST multipart/form-data из текстовых полей; сырой ответ.

        Возвращает ``httpx.Response`` без разбора тела: вызывающему могут
        быть нужны статус (201/303) и заголовки (Location). Статусы >= 400
        маппятся в HHError как обычно.
        """
        multipart = {name: (None, value) for name, value in fields.items()}
        return await self._send("POST", path, files=multipart)

    async def put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        """PUT-запрос к API hh.ru (без автоповторов)."""
        return await self._request("PUT", path, params=params, json=json, data=data, files=files)

    async def delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        """DELETE-запрос к API hh.ru (без автоповторов)."""
        return await self._request("DELETE", path, params=params, data=data, files=files)

    async def aclose(self) -> None:
        """Закрывает underlying-клиент."""
        await self._client.aclose()

    async def __aenter__(self) -> HHClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
