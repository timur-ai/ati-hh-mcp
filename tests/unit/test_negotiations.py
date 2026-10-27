"""Тесты набора инструментов «negotiations» против MockTransport."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastmcp import Client, FastMCP

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets import negotiations as neg

from ..conftest import MockHH, make_config

TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "list_negotiations": neg.LIST_NEGOTIATIONS,
    "get_negotiation": neg.GET_NEGOTIATION,
    "update_negotiation": neg.UPDATE_NEGOTIATION,
    "move_negotiation": neg.MOVE_NEGOTIATION,
    "list_negotiation_messages": neg.LIST_NEGOTIATION_MESSAGES,
    "send_negotiation_message": neg.SEND_NEGOTIATION_MESSAGE,
    "list_collection_negotiations": neg.LIST_COLLECTION_NEGOTIATIONS,
    "mark_negotiations_read": neg.MARK_NEGOTIATIONS_READ,
    "request_phone_interview": neg.REQUEST_PHONE_INTERVIEW,
    "get_negotiation_test_solution": neg.GET_NEGOTIATION_TEST_SOLUTION,
}

MUTATIONS = frozenset(
    {
        "update_negotiation",
        "move_negotiation",
        "send_negotiation_message",
        "mark_negotiations_read",
        "request_phone_interview",
    }
)


def _json_body(request: httpx.Request) -> Any:
    return json.loads(request.content)


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


async def test_list_negotiations_query_params(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": [], "found": 3}
    result = await neg.LIST_NEGOTIATIONS(
        status="considering",
        vacancy_id="771",
        order_by="updated_at",
        order="desc",
        has_updates=True,
        with_job_search_status=True,
        page=1,
        per_page=25,
    )
    assert result["found"] == 3
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/negotiations"
    assert dict(request.url.params) == {
        "status": "considering",
        "vacancy_id": "771",
        "order_by": "updated_at",
        "order": "desc",
        "has_updates": "true",
        "with_job_search_status": "true",
        "page": "1",
        "per_page": "25",
    }


async def test_list_negotiations_empty_query(mock_hh: MockHH) -> None:
    await neg.LIST_NEGOTIATIONS()
    assert dict(mock_hh.requests[-1].url.params) == {}


async def test_get_negotiation_path_substitution(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "42", "state": "considering"}
    result = await neg.GET_NEGOTIATION(id="42")
    assert result["id"] == "42"
    request = mock_hh.requests[-1]
    assert request.url.path == "/negotiations/42"
    assert dict(request.url.params) == {}  # id ушёл в путь, не в query.


async def test_update_negotiation_sends_body(mock_hh: MockHH) -> None:
    await neg.UPDATE_NEGOTIATION(
        id="considering",
        body={"topic_id": "42", "message": "Приглашаем"},
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/negotiations/considering"
    assert dict(request.url.params) == {}
    assert _json_body(request) == {"topic_id": "42", "message": "Приглашаем"}


async def test_move_negotiation_two_path_params(mock_hh: MockHH) -> None:
    await neg.MOVE_NEGOTIATION(
        collection_name="invitation",
        nid="7",
        body={"message": "hello"},
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/negotiations/invitation/7"
    assert _json_body(request) == {"message": "hello"}


async def test_move_negotiation_without_body(mock_hh: MockHH) -> None:
    """Тело опционально: запрос уходит без JSON-тела."""
    await neg.MOVE_NEGOTIATION(collection_name="declined", nid="7", confirm=True)
    request = mock_hh.requests[-1]
    assert request.url.path == "/negotiations/declined/7"
    assert request.content == b""


async def test_list_negotiation_messages(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await neg.LIST_NEGOTIATION_MESSAGES(nid="9", with_text_only=True, page=0, per_page=50)
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/negotiations/9/messages"
    assert dict(request.url.params) == {
        "with_text_only": "true",
        "page": "0",
        "per_page": "50",
    }


async def test_send_negotiation_message(mock_hh: MockHH) -> None:
    await neg.SEND_NEGOTIATION_MESSAGE(nid="9", body={"message": "готов выйти"}, confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/negotiations/9/messages"
    assert _json_body(request) == {"message": "готов выйти"}


async def test_list_collection_negotiations_filters(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await neg.LIST_COLLECTION_NEGOTIATIONS(
        vacancy_id="771",
        area="1,2",
        experience="between3And6",
        salary_from=100000.0,
        salary_to=200000.0,
        currency="RUR",
        show_only_new_responses=True,
        page=1,
    )
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/negotiations/response"
    assert dict(request.url.params) == {
        "vacancy_id": "771",
        "area": "1,2",
        "experience": "between3And6",
        "salary_from": "100000.0",
        "salary_to": "200000.0",
        "currency": "RUR",
        "show_only_new_responses": "true",
        "page": "1",
    }


async def test_mark_negotiations_read(mock_hh: MockHH) -> None:
    await neg.MARK_NEGOTIATIONS_READ(body={"topic_id": "42"}, confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/negotiations/read"
    assert _json_body(request) == {"topic_id": "42"}


async def test_request_phone_interview_form_body(mock_hh: MockHH) -> None:
    """Спека декларирует x-www-form-urlencoded: тело – form-encoded,
    bool приводится к true/false (стиль JSON)."""
    await neg.REQUEST_PHONE_INTERVIEW(
        body={"resume_id": "123", "vacancy_id": "456", "send_sms": True},
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/negotiations/phone_interview"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.read().decode()) == {
        "resume_id": ["123"],
        "vacancy_id": ["456"],
        "send_sms": ["true"],
    }


async def test_get_negotiation_test_solution(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"solutions": []}
    await neg.GET_NEGOTIATION_TEST_SOLUTION(nid="3")
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/negotiations/3/test/solution"
    assert dict(request.url.params) == {}


@pytest.mark.parametrize(
    ("tool_name", "kwargs"),
    [
        ("update_negotiation", {"id": "x", "body": {"topic_id": "1"}}),
        ("move_negotiation", {"collection_name": "invitation", "nid": "1"}),
        ("send_negotiation_message", {"nid": "1", "body": {"message": "m"}}),
        ("mark_negotiations_read", {"body": {"topic_id": "1"}}),
        ("request_phone_interview", {"body": {"resume_id": "1", "vacancy_id": "2"}}),
    ],
)
async def test_mutations_require_confirm(
    mock_hh: MockHH, tool_name: str, kwargs: dict[str, Any]
) -> None:
    """Мутация без confirm=True – структурированная ошибка, запрос не уходит."""
    with pytest.raises(HHError) as exc_info:
        await TOOLS[tool_name](**kwargs)
    assert exc_info.value.code == "confirm_required"
    assert mock_hh.requests == []


async def test_body_dict_flattened_through_mcp_layer(mock_hh: MockHH) -> None:
    """Через реальный MCP-клиент body приходит dict-ом и уходит в JSON."""
    mock_hh.json_response = {"items": []}
    server = FastMCP(name="test-negotiations")
    neg.register(server)
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))
    async with Client(server) as client:
        await client.call_tool(
            "send_negotiation_message",
            {"nid": "9", "body": {"message": "через MCP"}, "confirm": True},
        )
    request = mock_hh.requests[-1]
    assert request.url.path == "/negotiations/9/messages"
    assert _json_body(request) == {"message": "через MCP"}


def test_registry_entries_and_flags() -> None:
    entries = REGISTRY.by_toolset("negotiations")
    assert sorted(e.name for e in entries) == sorted(TOOLS)
    assert len(entries) == 10
    for entry in entries:
        assert entry.requires_auth is True, entry.name
        assert entry.is_mutation == (entry.name in MUTATIONS), entry.name


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "GET /negotiations",
        "GET /negotiations/{id}",
        "PUT /negotiations/{id}",
        "PUT /negotiations/{collection_name}/{nid}",
        "GET /negotiations/{nid}/messages",
        "POST /negotiations/{nid}/messages",
        "GET /negotiations/response",
        "POST /negotiations/read",
        "POST /negotiations/phone_interview",
        "GET /negotiations/{nid}/test/solution",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None
