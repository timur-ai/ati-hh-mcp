"""HTTP-клиент к API hh.ru: заголовки, таймауты, маппинг ошибок.

Троттлинг и автоматические повторы (GET + 429) появятся на этапе M2;
здесь закладывается структура с единым методом ``_request``.
"""

from __future__ import annotations

from typing import Any

import httpx

from .. import __version__
from ..config import Config
from .errors import error_from_response

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0


def user_agent(ua_email: str) -> str:
    """User-Agent по требованию hh.ru: приложение/версия и контактный email."""
    return f"ati-hh-mcp/{__version__} ({ua_email})"


class HHClient:
    """Тонкая обёртка над httpx.AsyncClient для API hh.ru."""

    def __init__(
        self,
        config: Config,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
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

    @property
    def base_url(self) -> str:
        """Базовый URL API (для тестов и диагностики)."""
        return str(self._client.base_url)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Единая точка запроса: здесь появятся троттлинг и повторы (M2)."""
        response = await self._client.request(method, path, params=params, json=json)
        if response.status_code >= 400:
            try:
                body: Any = response.json()
            except ValueError:
                body = None
            raise error_from_response(response.status_code, body) from None
        if not response.content:
            return None
        return response.json()

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """GET-запрос к API hh.ru."""
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """POST-запрос к API hh.ru."""
        return await self._request("POST", path, params=params, json=json)

    async def put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """PUT-запрос к API hh.ru."""
        return await self._request("PUT", path, params=params, json=json)

    async def delete(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """DELETE-запрос к API hh.ru."""
        return await self._request("DELETE", path, params=params)

    async def aclose(self) -> None:
        """Закрывает underlying-клиент."""
        await self._client.aclose()

    async def __aenter__(self) -> HHClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
