"""Тесты набора инструментов «employer_managers» против MockTransport."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets.employer_managers import (
    EMPLOYER_CREATE_MANAGER,
    EMPLOYER_DELETE_MANAGER,
    EMPLOYER_GET_MANAGER,
    EMPLOYER_GET_MANAGER_METHOD_ACCESS,
    EMPLOYER_GET_MANAGER_RESUME_LIMITS,
    EMPLOYER_GET_MANAGER_SETTINGS,
    EMPLOYER_GET_MANAGER_VACANCY_TYPES,
    EMPLOYER_LIST_MANAGER_TYPES,
    EMPLOYER_LIST_MANAGERS,
    EMPLOYER_UPDATE_MANAGER,
    GET_MY_MANAGER_ACCOUNTS,
)

from ..conftest import MockHH, make_config

READ_TOOLS = frozenset(
    {
        "employer_list_managers",
        "employer_get_manager",
        "employer_list_manager_types",
        "employer_get_manager_resume_limits",
        "employer_get_manager_method_access",
        "employer_get_manager_settings",
        "employer_get_manager_vacancy_types",
        "get_my_manager_accounts",
    }
)

MUTATIONS = frozenset(
    {
        "employer_create_manager",
        "employer_update_manager",
        "employer_delete_manager",
    }
)


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


async def test_list_managers_query_and_path(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": [], "found": 2, "page": 0, "pages": 1}
    result = await EMPLOYER_LIST_MANAGERS(
        employer_id="1455", page=0, per_page=100, search_text="Иван"
    )
    assert result["found"] == 2
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/employers/1455/managers"
    assert dict(request.url.params) == {
        "page": "0",
        "per_page": "100",
        "search_text": "Иван",
    }


async def test_create_manager_body_json(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "87654321"}
    await EMPLOYER_CREATE_MANAGER(
        employer_id="1455",
        body={
            "emails": ["new.manager@example.com"],
            "manager_type": {"id": "3"},
            "is_admin": False,
        },
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/employers/1455/managers"
    assert dict(request.url.params) == {}
    assert json.loads(request.read()) == {
        "emails": ["new.manager@example.com"],
        "manager_type": {"id": "3"},
        "is_admin": False,
    }


async def test_get_manager_path_substitution(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "87654321", "full_name": "Иван Петров"}
    result = await EMPLOYER_GET_MANAGER(employer_id="1455", manager_id="87654321")
    assert result["id"] == "87654321"
    request = mock_hh.requests[-1]
    assert request.url.path == "/employers/1455/managers/87654321"
    assert dict(request.url.params) == {}


async def test_update_manager_body_json(mock_hh: MockHH) -> None:
    mock_hh.json_response = None
    await EMPLOYER_UPDATE_MANAGER(
        employer_id="1455",
        manager_id="87654321",
        body={"manager_type": {"id": "5"}},
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/employers/1455/managers/87654321"
    assert dict(request.url.params) == {}
    assert json.loads(request.read()) == {"manager_type": {"id": "5"}}


async def test_delete_manager_successor_id_in_query(mock_hh: MockHH) -> None:
    """successor_id – обязательный query-параметр удаления менеджера."""
    mock_hh.json_response = None
    await EMPLOYER_DELETE_MANAGER(
        employer_id="1455", manager_id="87654321", successor_id="11112222", confirm=True
    )
    request = mock_hh.requests[-1]
    assert request.method == "DELETE"
    assert request.url.path == "/employers/1455/managers/87654321"
    assert dict(request.url.params) == {"successor_id": "11112222"}


async def test_delete_manager_requires_successor_id(mock_hh: MockHH) -> None:
    """Обязательный successor_id не имеет значения по умолчанию."""
    signature = EMPLOYER_DELETE_MANAGER.__signature__  # type: ignore[attr-defined]
    param = signature.parameters["successor_id"]
    assert param.default is param.empty


async def test_list_manager_types(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_LIST_MANAGER_TYPES(employer_id="1455")
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/employers/1455/manager_types"
    assert dict(request.url.params) == {}


async def test_get_manager_resume_limits(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"daily_limit": 100, "resumes_left": 42}
    result = await EMPLOYER_GET_MANAGER_RESUME_LIMITS(employer_id="1455", manager_id="87654321")
    assert result["resumes_left"] == 42
    request = mock_hh.requests[-1]
    assert request.url.path == "/employers/1455/managers/87654321/limits/resume"


async def test_get_manager_method_access(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_GET_MANAGER_METHOD_ACCESS(employer_id="1455", manager_id="87654321")
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/employers/1455/managers/87654321/method_access"


async def test_get_manager_settings(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"default_vacancy_branded_template": None}
    await EMPLOYER_GET_MANAGER_SETTINGS(employer_id="1455", manager_id="87654321")
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/employers/1455/managers/87654321/settings"


async def test_get_manager_vacancy_types(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_GET_MANAGER_VACANCY_TYPES(employer_id="1455", manager_id="87654321")
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == ("/employers/1455/managers/87654321/vacancies/available_types")


async def test_get_my_manager_accounts_no_params(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": [], "main": None}
    result = await GET_MY_MANAGER_ACCOUNTS()
    assert result["items"] == []
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/manager_accounts/mine"
    assert dict(request.url.params) == {}


# --- confirm и реестр -------------------------------------------------------


_MUTATION_MINIMAL_ARGS: dict[str, dict[str, Any]] = {
    "employer_create_manager": {"employer_id": "1455", "body": {"emails": ["a@b.c"]}},
    "employer_update_manager": {
        "employer_id": "1455",
        "manager_id": "87654321",
        "body": {"emails": ["a@b.c"]},
    },
    "employer_delete_manager": {
        "employer_id": "1455",
        "manager_id": "87654321",
        "successor_id": "11112222",
    },
}

_MUTATION_TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "employer_create_manager": EMPLOYER_CREATE_MANAGER,
    "employer_update_manager": EMPLOYER_UPDATE_MANAGER,
    "employer_delete_manager": EMPLOYER_DELETE_MANAGER,
}


@pytest.mark.parametrize("tool_name", sorted(MUTATIONS))
async def test_mutations_require_confirm(tool_name: str, mock_hh: MockHH) -> None:
    """Без confirm=True – структурированная ошибка, HTTP не выполняется."""
    tool = _MUTATION_TOOLS[tool_name]
    with pytest.raises(HHError) as excinfo:
        await tool(**_MUTATION_MINIMAL_ARGS[tool_name])
    assert excinfo.value.code == "confirm_required"
    assert "confirm=True" in excinfo.value.description
    assert mock_hh.requests == []


def test_registry_entries_and_flags() -> None:
    entries = REGISTRY.by_toolset("employer_managers")
    assert len(entries) == 11
    assert sorted(e.name for e in entries) == sorted(MUTATIONS | READ_TOOLS)
    for entry in entries:
        assert entry.requires_auth is True, entry.name
        assert entry.is_mutation is (entry.name in MUTATIONS), entry.name


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "GET /employers/{employer_id}/managers",
        "POST /employers/{employer_id}/managers",
        "GET /employers/{employer_id}/managers/{manager_id}",
        "PUT /employers/{employer_id}/managers/{manager_id}",
        "DELETE /employers/{employer_id}/managers/{manager_id}",
        "GET /employers/{employer_id}/manager_types",
        "GET /employers/{employer_id}/managers/{manager_id}/limits/resume",
        "GET /employers/{employer_id}/managers/{manager_id}/method_access",
        "GET /employers/{employer_id}/managers/{manager_id}/settings",
        "GET /employers/{employer_id}/managers/{manager_id}/vacancies/available_types",
        "GET /manager_accounts/mine",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None
