"""Тесты набора инструментов «dictionaries» против MockTransport."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets import dictionaries

from ..conftest import MockHH, make_config

# Инструмент -> (ожидаемый путь при вызове, kwargs, ожидаемые query).
CASES: dict[str, tuple[str, dict[str, Any], dict[str, str]]] = {
    "dict_dictionaries": ("/dictionaries", {}, {}),
    "dict_areas": ("/areas", {}, {}),
    "dict_areas_with_case": (
        "/areas",
        {"additional_case": "prepositional"},
        {"additional_case": "prepositional"},
    ),
    "dict_area_countries": ("/areas/countries", {}, {}),
    "dict_area": ("/areas/113", {"area_id": "113"}, {}),
    "dict_area_with_case": (
        "/areas/113",
        {"area_id": "113", "additional_case": "prepositional"},
        {"additional_case": "prepositional"},
    ),
    "dict_industries": ("/industries", {}, {}),
    "dict_professional_roles": ("/professional_roles", {}, {}),
    "dict_languages": ("/languages", {}, {}),
    "dict_locales": ("/locales", {}, {}),
    "dict_resume_locales": ("/locales/resume", {}, {}),
    "dict_districts": ("/districts", {}, {}),
    "dict_metro": ("/metro", {}, {}),
    "dict_metro_city": ("/metro/4", {"city_id": "4"}, {}),
    "dict_skills": ("/skills", {"id": "2716"}, {"id": "2716"}),
    "dict_educational_institutions": (
        "/educational_institutions",
        {"id": "39306"},
        {"id": "39306"},
    ),
    "dict_faculties": (
        "/educational_institutions/39306/faculties",
        {"id": "39306"},
        {},
    ),
    "dict_vacancy_conditions": ("/vacancy_conditions", {}, {}),
}

ALL_TOOL_NAMES = sorted(
    {
        "dict_dictionaries",
        "dict_areas",
        "dict_area_countries",
        "dict_area",
        "dict_industries",
        "dict_professional_roles",
        "dict_languages",
        "dict_locales",
        "dict_resume_locales",
        "dict_districts",
        "dict_metro",
        "dict_metro_city",
        "dict_skills",
        "dict_educational_institutions",
        "dict_faculties",
        "dict_vacancy_conditions",
    }
)


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


def _tool(name: str) -> Callable[..., Awaitable[Any]]:
    for tool in dictionaries._TOOLS:
        if tool.__name__ == name:
            return tool
    raise KeyError(name)


@pytest.mark.parametrize("case_name", sorted(CASES))
async def test_tool_request_and_query(mock_hh: MockHH, case_name: str) -> None:
    tool_name = case_name.removesuffix("_with_case")
    mock_hh.json_response = {"payload": tool_name}
    expected_path, kwargs, expected_query = CASES[case_name]
    result = await _tool(tool_name)(**kwargs)
    assert result == {"payload": tool_name}
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == expected_path
    assert dict(request.url.params) == expected_query


def test_toolset_name_and_contract() -> None:
    assert dictionaries.TOOLSET_NAME == "dictionaries"
    assert hasattr(dictionaries, "register")


def test_all_sixteen_registered_in_registry() -> None:
    entries = REGISTRY.by_toolset("dictionaries")
    assert sorted(e.name for e in entries) == ALL_TOOL_NAMES
    assert len(entries) == 16


def test_registry_entries_flags() -> None:
    for name in ALL_TOOL_NAMES:
        entry = REGISTRY.get(name)
        assert entry is not None, name
        assert entry.toolset == "dictionaries"
        assert entry.requires_auth is False
        assert entry.is_mutation is False
        assert entry.undocumented is False


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "GET /dictionaries",
        "GET /areas",
        "GET /areas/countries",
        "GET /areas/{area_id}",
        "GET /industries",
        "GET /professional_roles",
        "GET /languages",
        "GET /locales",
        "GET /locales/resume",
        "GET /districts",
        "GET /metro",
        "GET /metro/{city_id}",
        "GET /skills",
        "GET /educational_institutions",
        "GET /educational_institutions/{id}/faculties",
        "GET /vacancy_conditions",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None, operation_id
