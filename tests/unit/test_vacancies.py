"""Тесты набора инструментов «vacancies» против MockTransport."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastmcp import Client

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.server import build_server
from ati_hh_mcp.toolsets.vacancies import (
    GET_VACANCY,
    RELATED_VACANCIES,
    SEARCH_VACANCIES,
    SIMILAR_VACANCIES,
    SimilarVacanciesAdvanced,
    VacancySearchAdvanced,
)

from ..conftest import MockHH, make_config

TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "search_vacancies": SEARCH_VACANCIES,
    "get_vacancy": GET_VACANCY,
    "similar_vacancies": SIMILAR_VACANCIES,
    "related_vacancies": RELATED_VACANCIES,
}


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


async def test_search_vacancies_frequent_params(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": [], "found": 5, "page": 0, "pages": 1}
    result = await SEARCH_VACANCIES(
        text="python",
        area="1,2",
        salary=150000.0,
        currency="RUR",
        experience="between1And3",
        employment="full",
        schedule="remote",
        search_field="name",
        page=2,
        per_page=50,
        order_by="publication_time",
    )
    assert result["found"] == 5
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/vacancies"
    assert dict(request.url.params) == {
        "text": "python",
        "area": "1,2",
        "salary": "150000.0",
        "currency": "RUR",
        "experience": "between1And3",
        "employment": "full",
        "schedule": "remote",
        "search_field": "name",
        "page": "2",
        "per_page": "50",
        "order_by": "publication_time",
    }


async def test_search_vacancies_advanced_only_set_fields(mock_hh: MockHH) -> None:
    """Вложенная advanced-модель: в запрос попадают только заданные поля."""
    mock_hh.json_response = {"items": []}
    await SEARCH_VACANCIES(
        text="data engineer",
        advanced=VacancySearchAdvanced(
            date_from="2026-01-01",
            clusters=True,
            work_format="remote",
            top_lat=56.0,
        ),
    )
    params = dict(mock_hh.requests[-1].url.params)
    assert params == {
        "text": "data engineer",
        "date_from": "2026-01-01",
        "clusters": "true",
        "work_format": "remote",
        "top_lat": "56.0",
    }
    # Незаданные поля хвоста не попадают в запрос.
    assert "education" not in params
    assert "no_magic" not in params


async def test_search_vacancies_no_unnecessary_query(mock_hh: MockHH) -> None:
    """Вызов без параметров: query полностью пуст (None не отправляется)."""
    await SEARCH_VACANCIES()
    assert dict(mock_hh.requests[-1].url.params) == {}


async def test_get_vacancy_path_substitution(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "123", "name": "Senior Python"}
    result = await GET_VACANCY(vacancy_id="123")
    assert result["id"] == "123"
    request = mock_hh.requests[-1]
    assert request.url.path == "/vacancies/123"
    assert dict(request.url.params) == {}  # vacancy_id ушёл в путь, не в query.


async def test_similar_vacancies_path_and_filters(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await SIMILAR_VACANCIES(
        vacancy_id="42",
        area="1",
        advanced=SimilarVacanciesAdvanced(excluded_employer_id="77", part_time="part"),
    )
    request = mock_hh.requests[-1]
    assert request.url.path == "/vacancies/42/similar_vacancies"
    assert dict(request.url.params) == {
        "area": "1",
        "excluded_employer_id": "77",
        "part_time": "part",
    }


async def test_related_vacancies_path_and_filters(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await RELATED_VACANCIES(vacancy_id="42", per_page=5)
    request = mock_hh.requests[-1]
    assert request.url.path == "/vacancies/42/related_vacancies"
    assert dict(request.url.params) == {"per_page": "5"}


async def test_advanced_dict_from_mcp_layer_is_flattened(mock_hh: MockHH) -> None:
    """Через реальный MCP-клиент advanced приходит dict-ом и разворачивается."""
    mock_hh.json_response = {"items": []}
    config = make_config(toolsets=("vacancies",))
    server = build_server(config)
    toolkit.set_client_factory(lambda: HHClient(config, transport=mock_hh.transport))
    async with Client(server) as client:
        await client.call_tool(
            "search_vacancies",
            {"text": "go", "advanced": {"education": "higher", "no_magic": True}},
        )
    request = mock_hh.requests[-1]
    assert request.url.path == "/vacancies"
    assert dict(request.url.params) == {
        "text": "go",
        "education": "higher",
        "no_magic": "true",
    }


async def test_all_four_registered_with_flags() -> None:
    entries = REGISTRY.by_toolset("vacancies")
    assert sorted(e.name for e in entries) == sorted(TOOLS)
    assert len(entries) == 4
    for entry in entries:
        assert entry.requires_auth is False
        assert entry.is_mutation is False


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "GET /vacancies",
        "GET /vacancies/{vacancy_id}",
        "GET /vacancies/{vacancy_id}/similar_vacancies",
        "GET /vacancies/{vacancy_id}/related_vacancies",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None
