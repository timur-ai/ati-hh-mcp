"""Тесты набора инструментов «suggests» против MockTransport."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets import suggests

from ..conftest import MockHH, make_config

# Инструмент -> (путь эндпоинта, kwargs, ожидаемые query).
CASES: dict[str, tuple[str, dict[str, Any], dict[str, str]]] = {
    "suggest_areas": (
        "/suggests/areas",
        {"text": "Моск", "area_id": "1", "include_parent": True},
        {"text": "Моск", "area_id": "1", "include_parent": "true"},
    ),
    "suggest_area_leaves": (
        "/suggests/area_leaves",
        {"text": "Хим", "area_id": "1"},
        {"text": "Хим", "area_id": "1"},
    ),
    "suggest_companies": (
        "/suggests/companies",
        {"text": "Сбер"},
        {"text": "Сбер"},
    ),
    "suggest_educational_institutions": (
        "/suggests/educational_institutions",
        {"text": "МГУ"},
        {"text": "МГУ"},
    ),
    "suggest_fields_of_study": (
        "/suggests/fields_of_study",
        {"text": "прог"},
        {"text": "прог"},
    ),
    "suggest_positions": (
        "/suggests/positions",
        {"text": "инжен"},
        {"text": "инжен"},
    ),
    "suggest_professional_roles": (
        "/suggests/professional_roles",
        {"text": "аналит"},
        {"text": "аналит"},
    ),
    "suggest_resume_search_keyword": (
        "/suggests/resume_search_keyword",
        {"text": "python"},
        {"text": "python"},
    ),
    "suggest_skill_set": (
        "/suggests/skill_set",
        {"text": "docker"},
        {"text": "docker"},
    ),
    "suggest_vacancy_positions": (
        "/suggests/vacancy_positions",
        {"text": "разраб"},
        {"text": "разраб"},
    ),
    "suggest_vacancy_search_keyword": (
        "/suggests/vacancy_search_keyword",
        {"text": "аналитик данных"},
        {"text": "аналитик данных"},
    ),
}


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


def _tool(name: str) -> Callable[..., Awaitable[Any]]:
    for tool in suggests._TOOLS:
        if tool.__name__ == name:
            return tool
    raise KeyError(name)


@pytest.mark.parametrize("tool_name", sorted(CASES))
async def test_tool_request_and_query(mock_hh: MockHH, tool_name: str) -> None:
    path, kwargs, expected_query = CASES[tool_name]
    mock_hh.json_response = {"items": [{"text": "x"}]}
    result = await _tool(tool_name)(**kwargs)
    assert result == {"items": [{"text": "x"}]}
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == path
    assert dict(request.url.params) == expected_query


def test_text_is_required_for_plain_suggests() -> None:
    import inspect

    signature = inspect.signature(_tool("suggest_skill_set"))
    text_param = signature.parameters["text"]
    assert text_param.default is inspect.Parameter.empty  # обязательный text.


def test_all_eleven_registered_in_registry() -> None:
    entries = REGISTRY.by_toolset("suggests")
    assert len(entries) == 11
    assert sorted(e.name for e in entries) == sorted(CASES)


def test_registry_entries_flags() -> None:
    for name in CASES:
        entry = REGISTRY.get(name)
        assert entry is not None, name
        assert entry.toolset == "suggests"
        assert entry.requires_auth is False
        assert entry.is_mutation is False


def test_registry_lookup_by_operation() -> None:
    for path in CASES.values():
        assert REGISTRY.get_by_operation(f"GET {path[0]}") is not None
