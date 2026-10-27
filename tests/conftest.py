"""Общие фикстуры тестов."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from ati_hh_mcp.config import Config


def make_config(**overrides: Any) -> Config:
    """Конфигурация по умолчанию с точечными переопределениями."""
    defaults: dict[str, Any] = {
        "token": None,
        "toolsets": ("dictionaries",),
        "api_base": "https://api.hh.test",
        "ua_email": "owner@example.test",
        "client_id": None,
        "client_secret": None,
        "redirect_uri": None,
        "api_keys": (),
    }
    defaults.update(overrides)
    return Config(**defaults)


class MockHH:
    """Заглушка API hh.ru на httpx.MockTransport с записью запросов."""

    def __init__(self, *, json_response: Any = None, status_code: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.json_response = json_response if json_response is not None else {}
        self.status_code = status_code

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.json_response)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def base_config() -> Config:
    return make_config()


@pytest.fixture
def mock_hh() -> MockHH:
    return MockHH()
