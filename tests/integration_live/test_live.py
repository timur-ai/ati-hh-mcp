"""Живые интеграционные тесты: read-only вызовы к api.hh.ru через инструменты.

Маркер ``live``: дефолтный прогон их исключает (``addopts`` в pyproject);
запуск – ``uv run pytest -m live`` или CI-джоба live (workflow_dispatch /
еженедельный cron, секрет ``HH_LIVE_TOKEN``).

Правила (план, Expanded Test Plan → Integration live):
- только read-операции, ~10 запросов на прогон, вежливый троттлинг клиента;
- публичные справочники и подсказки – без токена;
- ``get_me``/``list_negotiations`` – только при заданном ``HH_LIVE_TOKEN``
  (иначе пропуск); отклики соискателя закрыты для новых приложений
  (hh.ru, 15.12.2025) – 403 forbidden превращается в skip;
- поисковые вакансии/работодатели с датацентрового IP гео-блокируются
  (403): единственный тест-индикатор превращает 403 в ``pytest.skip``,
  чтобы с домашнего IP поиск реально проверялся.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.client import CallToolResult
from fastmcp.exceptions import ToolError

from ati_hh_mcp import toolkit
from ati_hh_mcp.config import Config
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.server import build_server

pytestmark = pytest.mark.live

LIVE_API_BASE = "https://api.hh.ru"


def _payload(result: CallToolResult) -> Any:
    """JSON-результат вызова: structured data либо content-текст.

    Списочные ответы не попадают в MCP structuredContent (по спецификации
    он обязан быть объектом) – для них читаем text-контент.
    """
    if result.data is not None:
        return result.data
    return json.loads(result.content[0].text)


def _live_token() -> str | None:
    """Токен hh.ru из HH_LIVE_TOKEN (может отсутствовать – скипы)."""
    raw = os.environ.get("HH_LIVE_TOKEN", "").strip()
    return raw or None


@pytest.fixture
async def live_client() -> AsyncIterator[Client]:
    """In-memory MCP-клиент: инструменты + настоящий HHClient к api.hh.ru."""
    config = Config(
        token=_live_token(),
        toolsets=("auth", "dictionaries", "suggests", "vacancies", "negotiations"),
        api_base=LIVE_API_BASE,
        ua_email=os.environ.get("HH_UA_EMAIL", "timur.aribzhanov@mail.ru"),
        client_id=None,
        client_secret=None,
        redirect_uri=None,
        api_keys=(),
    )
    server = build_server(config)
    # Реальный клиент к живому API (троттлинг 25/мин – вежливость по умолчанию).
    toolkit.set_client_factory(lambda: HHClient(config))
    async with Client(server) as client:
        yield client


async def test_live_dictionaries(live_client: Client) -> None:
    result = await live_client.call_tool("dict_dictionaries", {})
    payload = _payload(result)
    assert "currency" in payload
    # Живой API отдаёт валюты списком объектов с полем code.
    currency = payload["currency"]
    codes = (
        {item["code"] for item in currency} if isinstance(currency, list) else set(currency)
    )
    assert "RUR" in codes


async def test_live_areas(live_client: Client) -> None:
    result = await live_client.call_tool("dict_areas", {})
    payload = _payload(result)
    assert isinstance(payload, list)
    # Верхний уровень – страны; Москва (id=1) вложена в Россию (id=113).
    russia = next(area for area in payload if area.get("id") == "113")
    assert any(sub.get("id") == "1" for sub in russia.get("areas", []))


async def test_live_industries(live_client: Client) -> None:
    result = await live_client.call_tool("dict_industries", {})
    payload = _payload(result)
    assert isinstance(payload, list)
    assert payload  # справочник непуст (id, name, sub-industries).


async def test_live_suggest_positions(live_client: Client) -> None:
    result = await live_client.call_tool("suggest_positions", {"text": "python"})
    payload = _payload(result)
    items = payload["items"] if isinstance(payload, dict) else payload
    assert items  # подсказка «python» непуста (например, «Программист Python»).


async def test_live_locales(live_client: Client) -> None:
    result = await live_client.call_tool("dict_locales", {})
    payload = _payload(result)
    assert isinstance(payload, list)
    assert any(locale.get("id") == "RU" for locale in payload)


@pytest.mark.skipif(not _live_token(), reason="HH_LIVE_TOKEN не задан")
async def test_live_get_me(live_client: Client) -> None:
    result = await live_client.call_tool("get_me", {})
    payload = _payload(result)
    assert "id" in payload
    assert "email" in payload


@pytest.mark.skipif(not _live_token(), reason="HH_LIVE_TOKEN не задан")
async def test_live_list_negotiations(live_client: Client) -> None:
    """Отклики/приглашения соискателя.

    С 15.12.2025 hh.ru закрыла API соискателей для новых приложений:
    даже валидный токен получает 403 forbidden на личных эндпоинтах
    соискателя (negotiations, resumes/mine). Такой ответ – честный skip;
    проверки остаются строгими, когда доступ есть.
    """
    try:
        result = await live_client.call_tool("list_negotiations", {"per_page": 3})
    except ToolError as error:
        if "[forbidden]" in str(error):
            pytest.skip("applicant API closed for new apps since 2025-12-15")
        raise
    payload = _payload(result)
    assert isinstance(payload.get("items"), list)
    assert len(payload["items"]) <= 3


async def test_live_search_vacancies_geo_indicator(live_client: Client) -> None:
    """Тест-индикатор гео-блокировки поиска с датацентрового IP.

    С домашнего IP поиск вакансий работает и тест зелёный; с датацентрового
    hh.ru отвечает 403 – честный skip вместо падения. Через MCP-клиент
    ошибка инструмента приходит как ToolError с текстом HHError
    (``[forbidden] ...``).
    """
    try:
        result = await live_client.call_tool(
            "search_vacancies", {"text": "python", "per_page": 1}
        )
    except ToolError as error:
        if "[forbidden]" in str(error):
            pytest.skip("geo-blocked from datacenter IP")
        raise
    payload = _payload(result)
    assert payload["found"] > 0
    assert 0 < len(payload["items"]) <= 1
