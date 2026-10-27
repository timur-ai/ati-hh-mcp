"""Тесты набора инструментов «dictionaries» против MockTransport."""

from __future__ import annotations

import pytest

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets import dictionaries

from ..conftest import MockHH, make_config

EXPECTED = {
    "dict_dictionaries": "/dictionaries",
    "dict_areas": "/areas",
    "dict_metro": "/metro",
}


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


@pytest.mark.parametrize("tool_name", sorted(EXPECTED))
async def test_tool_request_and_passthrough(mock_hh: MockHH, tool_name: str) -> None:
    mock_hh.json_response = {"payload": tool_name}
    tool = getattr(dictionaries, tool_name.upper())
    result = await tool()
    assert result == {"payload": tool_name}
    request = mock_hh.requests[0]
    assert request.method == "GET"
    assert request.url.path == EXPECTED[tool_name]
    assert dict(request.url.params) == {}


def test_all_three_registered_in_registry() -> None:
    for tool_name in EXPECTED:
        entry = REGISTRY.get(tool_name)
        assert entry is not None, tool_name
        assert entry.toolset == "dictionaries"
        assert entry.requires_auth is False
        assert entry.is_mutation is False
        assert entry.undocumented is False


def test_registry_lookup_by_operation() -> None:
    assert REGISTRY.get_by_operation("GET /dictionaries") is not None
    assert REGISTRY.get_by_operation("GET /areas") is not None
    assert REGISTRY.get_by_operation("GET /metro") is not None


def test_registry_contains_exactly_three_dictionary_tools() -> None:
    entries = REGISTRY.by_toolset("dictionaries")
    assert sorted(e.name for e in entries) == sorted(EXPECTED)
