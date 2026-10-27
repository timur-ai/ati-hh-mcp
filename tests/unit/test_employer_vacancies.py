"""Тесты набора инструментов «employer_vacancies» против MockTransport."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs

import pytest
from fastmcp import Client, FastMCP

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets.employer_vacancies import (
    EMPLOYER_ARCHIVE_VACANCY,
    EMPLOYER_CREATE_VACANCY,
    EMPLOYER_CREATE_VACANCY_DRAFT,
    EMPLOYER_DELETE_AUTO_PUBLICATION,
    EMPLOYER_DELETE_VACANCY_DRAFT,
    EMPLOYER_GET_PREFERRED_NEGOTIATIONS_ORDER,
    EMPLOYER_GET_PROLONGATE_INFO,
    EMPLOYER_GET_VACANCY_DRAFT,
    EMPLOYER_GET_VACANCY_STATS,
    EMPLOYER_GET_VACANCY_UPGRADES,
    EMPLOYER_GET_VACANCY_VISITORS,
    EMPLOYER_HIDE_VACANCY,
    EMPLOYER_LIST_ACTIVE_VACANCIES,
    EMPLOYER_LIST_ARCHIVED_VACANCIES,
    EMPLOYER_LIST_DRAFT_DUPLICATES,
    EMPLOYER_LIST_HIDDEN_VACANCIES,
    EMPLOYER_LIST_VACANCY_DRAFTS,
    EMPLOYER_PROLONGATE_VACANCY,
    EMPLOYER_PUBLISH_VACANCY_DRAFT,
    EMPLOYER_SET_PREFERRED_NEGOTIATIONS_ORDER,
    EMPLOYER_UNHIDE_VACANCY,
    EMPLOYER_UPDATE_VACANCY,
    EMPLOYER_UPDATE_VACANCY_DRAFT,
    register,
)

from ..conftest import MockHH, make_config

TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "employer_create_vacancy": EMPLOYER_CREATE_VACANCY,
    "employer_update_vacancy": EMPLOYER_UPDATE_VACANCY,
    "employer_get_prolongate_info": EMPLOYER_GET_PROLONGATE_INFO,
    "employer_prolongate_vacancy": EMPLOYER_PROLONGATE_VACANCY,
    "employer_list_active_vacancies": EMPLOYER_LIST_ACTIVE_VACANCIES,
    "employer_list_archived_vacancies": EMPLOYER_LIST_ARCHIVED_VACANCIES,
    "employer_archive_vacancy": EMPLOYER_ARCHIVE_VACANCY,
    "employer_list_hidden_vacancies": EMPLOYER_LIST_HIDDEN_VACANCIES,
    "employer_hide_vacancy": EMPLOYER_HIDE_VACANCY,
    "employer_unhide_vacancy": EMPLOYER_UNHIDE_VACANCY,
    "employer_list_vacancy_drafts": EMPLOYER_LIST_VACANCY_DRAFTS,
    "employer_create_vacancy_draft": EMPLOYER_CREATE_VACANCY_DRAFT,
    "employer_get_vacancy_draft": EMPLOYER_GET_VACANCY_DRAFT,
    "employer_update_vacancy_draft": EMPLOYER_UPDATE_VACANCY_DRAFT,
    "employer_delete_vacancy_draft": EMPLOYER_DELETE_VACANCY_DRAFT,
    "employer_publish_vacancy_draft": EMPLOYER_PUBLISH_VACANCY_DRAFT,
    "employer_list_draft_duplicates": EMPLOYER_LIST_DRAFT_DUPLICATES,
    "employer_delete_auto_publication": EMPLOYER_DELETE_AUTO_PUBLICATION,
    "employer_get_preferred_negotiations_order": EMPLOYER_GET_PREFERRED_NEGOTIATIONS_ORDER,
    "employer_set_preferred_negotiations_order": EMPLOYER_SET_PREFERRED_NEGOTIATIONS_ORDER,
    "employer_get_vacancy_stats": EMPLOYER_GET_VACANCY_STATS,
    "employer_get_vacancy_visitors": EMPLOYER_GET_VACANCY_VISITORS,
    "employer_get_vacancy_upgrades": EMPLOYER_GET_VACANCY_UPGRADES,
}

_VACANCY_BODY: dict[str, Any] = {
    "name": "Senior Python",
    "area": {"id": "1"},
    "type": {"id": "open"},
    "salary": {"from": 200000, "currency": "RUR"},
}


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


# --- публикация и редактирование --------------------------------------------


async def test_create_vacancy_query_and_body_split(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "123"}
    result = await EMPLOYER_CREATE_VACANCY(body=_VACANCY_BODY, ignore_duplicates=True, confirm=True)
    assert result["id"] == "123"
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/vacancies"
    # ignore_duplicates уходит в query, объект вакансии – в JSON-тело.
    assert dict(request.url.params) == {"ignore_duplicates": "true"}
    assert json.loads(request.read()) == _VACANCY_BODY


async def test_create_vacancy_requires_confirm(mock_hh: MockHH) -> None:
    with pytest.raises(HHError) as excinfo:
        await EMPLOYER_CREATE_VACANCY(body=_VACANCY_BODY)
    assert excinfo.value.code == "confirm_required"
    assert mock_hh.requests == []  # HTTP-вызов не выполнялся.


async def test_update_vacancy_path_query_body(mock_hh: MockHH) -> None:
    await EMPLOYER_UPDATE_VACANCY(
        vacancy_id="123",
        body=_VACANCY_BODY,
        ignore_duplicates=False,
        ignore_replacement_warning=True,
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/vacancies/123"
    assert dict(request.url.params) == {
        "ignore_duplicates": "false",
        "ignore_replacement_warning": "true",
    }
    assert json.loads(request.read()) == _VACANCY_BODY


# --- продление ---------------------------------------------------------------


async def test_get_prolongate_info(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"prolong": []}
    await EMPLOYER_GET_PROLONGATE_INFO(vacancy_id="9", publication_period=30)
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/vacancies/9/prolongate"
    assert dict(request.url.params) == {"publication_period": "30"}


async def test_prolongate_vacancy_query_period_empty_body(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "9"}
    await EMPLOYER_PROLONGATE_VACANCY(vacancy_id="9", publication_period=30, confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/vacancies/9/prolongate"
    # publication_period – query-параметр операции, тело не отправляется.
    assert dict(request.url.params) == {"publication_period": "30"}
    assert request.read() == b""


# --- списки активных/архивных/скрытых ---------------------------------------


async def test_list_active_vacancies_filters_and_pagination(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": [], "found": 2}
    await EMPLOYER_LIST_ACTIVE_VACANCIES(
        employer_id="777",
        text="python",
        area="1,2",
        manager_id="5",
        all_accessible=True,
        page=1,
        per_page=50,
        order_by="publication_time",
    )
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/employers/777/vacancies/active"
    assert dict(request.url.params) == {
        "text": "python",
        "area": "1,2",
        "manager_id": "5",
        "all_accessible": "true",
        "page": "1",
        "per_page": "50",
        "order_by": "publication_time",
    }


async def test_list_archived_vacancies(mock_hh: MockHH) -> None:
    await EMPLOYER_LIST_ARCHIVED_VACANCIES(employer_id="777", page=0, per_page=20)
    request = mock_hh.requests[-1]
    assert request.url.path == "/employers/777/vacancies/archived"
    assert dict(request.url.params) == {"page": "0", "per_page": "20"}


async def test_list_hidden_vacancies_manager_filter(mock_hh: MockHH) -> None:
    await EMPLOYER_LIST_HIDDEN_VACANCIES(employer_id="777", manager_id="5")
    request = mock_hh.requests[-1]
    assert request.url.path == "/employers/777/vacancies/hidden"
    assert dict(request.url.params) == {"manager_id": "5"}


async def test_archive_hide_unhide_vacancy(mock_hh: MockHH) -> None:
    await EMPLOYER_ARCHIVE_VACANCY(employer_id="777", vacancy_id="9", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/employers/777/vacancies/archived/9"
    assert dict(request.url.params) == {}
    assert request.read() == b""  # пустое тело операции не кодируется как {}.

    await EMPLOYER_HIDE_VACANCY(employer_id="777", vacancy_id="9", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/employers/777/vacancies/hidden/9"

    await EMPLOYER_UNHIDE_VACANCY(employer_id="777", vacancy_id="9", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "DELETE"
    assert request.url.path == "/employers/777/vacancies/hidden/9"


async def test_hide_vacancy_requires_confirm(mock_hh: MockHH) -> None:
    with pytest.raises(HHError) as excinfo:
        await EMPLOYER_HIDE_VACANCY(employer_id="777", vacancy_id="9")
    assert excinfo.value.code == "confirm_required"
    assert mock_hh.requests == []


# --- черновики ---------------------------------------------------------------


async def test_list_vacancy_drafts_pagination(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_LIST_VACANCY_DRAFTS(page=0, per_page=10)
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/vacancies/drafts"
    assert dict(request.url.params) == {"page": "0", "per_page": "10"}


async def test_create_vacancy_draft_body(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "1110031"}
    await EMPLOYER_CREATE_VACANCY_DRAFT(body=_VACANCY_BODY, confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/vacancies/drafts"
    assert dict(request.url.params) == {}
    assert json.loads(request.read()) == _VACANCY_BODY


async def test_get_vacancy_draft(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "1110031", "name": "Senior Python"}
    result = await EMPLOYER_GET_VACANCY_DRAFT(draft_id="1110031")
    assert result["id"] == "1110031"
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/vacancies/drafts/1110031"
    assert dict(request.url.params) == {}


async def test_update_vacancy_draft_path_and_body(mock_hh: MockHH) -> None:
    await EMPLOYER_UPDATE_VACANCY_DRAFT(draft_id="1110031", body=_VACANCY_BODY, confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/vacancies/drafts/1110031"
    assert json.loads(request.read()) == _VACANCY_BODY


async def test_delete_vacancy_draft_confirm_and_path(mock_hh: MockHH) -> None:
    with pytest.raises(HHError):
        await EMPLOYER_DELETE_VACANCY_DRAFT(draft_id="1110031")
    assert mock_hh.requests == []

    await EMPLOYER_DELETE_VACANCY_DRAFT(draft_id="1110031", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "DELETE"
    assert request.url.path == "/vacancies/drafts/1110031"


async def test_publish_vacancy_draft_empty_body(mock_hh: MockHH) -> None:
    mock_hh.json_response = [123]
    await EMPLOYER_PUBLISH_VACANCY_DRAFT(draft_id="1110031", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/vacancies/drafts/1110031/publish"
    assert dict(request.url.params) == {}
    assert request.read() == b""


async def test_list_draft_duplicates(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_LIST_DRAFT_DUPLICATES(draft_id="1110031")
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/vacancies/drafts/1110031/duplicates"


async def test_delete_auto_publication_required_draft_id(mock_hh: MockHH) -> None:
    await EMPLOYER_DELETE_AUTO_PUBLICATION(draft_id="1110031", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "DELETE"
    assert request.url.path == "/vacancies/auto_publication"
    assert dict(request.url.params) == {"draft_id": "1110031"}


# --- сортировка откликов, статистика ----------------------------------------


async def test_get_preferred_negotiations_order_path_id(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"order_type": {"id": "last_change_time"}}
    await EMPLOYER_GET_PREFERRED_NEGOTIATIONS_ORDER(id="555")
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/vacancies/555/preferred_negotiations_order"
    assert dict(request.url.params) == {}  # id ушёл в путь, не в query.


async def test_set_preferred_negotiations_order_form_body(mock_hh: MockHH) -> None:
    """Спека декларирует x-www-form-urlencoded – тело уходит form-encoded."""
    await EMPLOYER_SET_PREFERRED_NEGOTIATIONS_ORDER(
        id="555", body={"order": "last_change_time"}, confirm=True
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/vacancies/555/preferred_negotiations_order"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.read().decode()) == {"order": ["last_change_time"]}


async def test_get_vacancy_stats(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"views": 100}
    result = await EMPLOYER_GET_VACANCY_STATS(vacancy_id="9")
    assert result["views"] == 100
    request = mock_hh.requests[-1]
    assert request.url.path == "/vacancies/9/stats"


async def test_get_vacancy_visitors_pagination(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_GET_VACANCY_VISITORS(vacancy_id="9", page=2, per_page=10)
    request = mock_hh.requests[-1]
    assert request.url.path == "/vacancies/9/visitors"
    assert dict(request.url.params) == {"page": "2", "per_page": "10"}


async def test_get_vacancy_upgrades(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_GET_VACANCY_UPGRADES(vacancy_id="9")
    request = mock_hh.requests[-1]
    assert request.url.path == "/vacancies/9/upgrades"


# --- контракт набора и реестр ------------------------------------------------


async def test_register_lists_all_tools_on_server(mock_hh: MockHH) -> None:
    """register() подключает все 23 инструмента (контракт волны 2)."""
    server = FastMCP(name="test-employer-vacancies")
    register(server, lambda: HHClient(make_config(), transport=mock_hh.transport))
    async with Client(server) as client:
        tools = await client.list_tools()
    assert {tool.name for tool in tools} == set(TOOLS)


async def test_create_vacancy_body_dict_from_mcp_layer(mock_hh: MockHH) -> None:
    """Через реальный MCP-клиент body приходит dict-ом и уходит в JSON."""
    mock_hh.json_response = {"id": "123"}
    server = FastMCP(name="test-employer-vacancies-mcp")
    register(server, lambda: HHClient(make_config(), transport=mock_hh.transport))
    async with Client(server) as client:
        await client.call_tool(
            "employer_create_vacancy",
            {"body": _VACANCY_BODY, "ignore_duplicates": True, "confirm": True},
        )
    request = mock_hh.requests[-1]
    assert request.url.path == "/vacancies"
    assert dict(request.url.params) == {"ignore_duplicates": "true"}
    assert json.loads(request.read()) == _VACANCY_BODY


def test_registry_entries_and_flags() -> None:
    entries = REGISTRY.by_toolset("employer_vacancies")
    assert len(entries) == 23
    assert sorted(e.name for e in entries) == sorted(TOOLS)
    for entry in entries:
        assert entry.requires_auth is True, entry.name
        method = entry.operation_id.split(" ", 1)[0]
        assert entry.is_mutation is (method != "GET"), entry.name


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "POST /vacancies",
        "PUT /vacancies/{vacancy_id}",
        "GET /employers/{employer_id}/vacancies/active",
        "PUT /employers/{employer_id}/vacancies/hidden/{vacancy_id}",
        "DELETE /vacancies/auto_publication",
        "PUT /vacancies/{id}/preferred_negotiations_order",
        "GET /vacancies/{vacancy_id}/upgrades",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None
