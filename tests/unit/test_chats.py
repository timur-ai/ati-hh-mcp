"""Тесты набора инструментов «chats» против MockTransport."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from fastmcp import Client, FastMCP

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets import chats

from ..conftest import MockHH, make_config

TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "list_chats": chats.LIST_CHATS,
    "get_unread_counters": chats.GET_UNREAD_COUNTERS,
    "get_chat_file_conditions": chats.GET_CHAT_FILE_CONDITIONS,
    "create_chat_file_upload_link": chats.CREATE_CHAT_FILE_UPLOAD_LINK,
    "create_chat_without_vacancy": chats.CREATE_CHAT_WITHOUT_VACANCY,
    "leave_chat": chats.LEAVE_CHAT,
    "mark_chat_message_read": chats.MARK_CHAT_MESSAGE_READ,
    "list_chat_messages": chats.LIST_CHAT_MESSAGES,
    "send_chat_message": chats.SEND_CHAT_MESSAGE,
    "update_chat_message": chats.UPDATE_CHAT_MESSAGE,
    "delete_chat_message": chats.DELETE_CHAT_MESSAGE,
    "get_chat_participants": chats.GET_CHAT_PARTICIPANTS,
    "update_chat_participants": chats.UPDATE_CHAT_PARTICIPANTS,
    "set_chat_write_possibility": chats.SET_CHAT_WRITE_POSSIBILITY,
}

READ_ONLY = frozenset(
    {
        "list_chats",
        "get_unread_counters",
        "get_chat_file_conditions",
        "list_chat_messages",
        "get_chat_participants",
    }
)


def _json_body(request: httpx.Request) -> Any:
    return json.loads(request.content)


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


async def test_list_chats_filters(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": [], "found": 2}
    result = await chats.LIST_CHATS(
        page=1,
        per_page=50,
        filter_unread=True,
        filter_has_text_message=False,
        vacancy_status="active",
        filter_with_vacancy_ids="[1,2,3]",
    )
    assert result["found"] == 2
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/common/chats"
    assert dict(request.url.params) == {
        "page": "1",
        "per_page": "50",
        "filter_unread": "true",
        "filter_has_text_message": "false",
        "vacancy_status": "active",
        "filter_with_vacancy_ids": "[1,2,3]",
    }


async def test_get_unread_counters_no_query(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"chats_count": 3, "messages_count": 7}
    result = await chats.GET_UNREAD_COUNTERS()
    assert result == {"chats_count": 3, "messages_count": 7}
    request = mock_hh.requests[-1]
    assert request.url.path == "/common/chats/counters/unread"
    assert dict(request.url.params) == {}


async def test_get_chat_file_conditions(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"formats": ["pdf"]}
    await chats.GET_CHAT_FILE_CONDITIONS()
    request = mock_hh.requests[-1]
    assert request.url.path == "/common/chats/files/conditions"
    assert dict(request.url.params) == {}


async def test_create_chat_file_upload_link_with_body(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"url": "https://upload.test"}
    result = await chats.CREATE_CHAT_FILE_UPLOAD_LINK(
        body={"file_name": "cv.pdf"}, confirm=True
    )
    assert result["url"] == "https://upload.test"
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/common/chats/files/upload_links"
    assert _json_body(request) == {"file_name": "cv.pdf"}


async def test_create_chat_file_upload_link_without_body(mock_hh: MockHH) -> None:
    """Тело опционально: запрос уходит без JSON-тела."""
    await chats.CREATE_CHAT_FILE_UPLOAD_LINK(confirm=True)
    request = mock_hh.requests[-1]
    assert request.url.path == "/common/chats/files/upload_links"
    assert request.content == b""


async def test_create_chat_without_vacancy(mock_hh: MockHH) -> None:
    await chats.CREATE_CHAT_WITHOUT_VACANCY(
        body={"resume_hash": "abc", "first_message": "привет"}, confirm=True
    )
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/common/chats/without_vacancy"
    assert _json_body(request) == {"resume_hash": "abc", "first_message": "привет"}


async def test_leave_chat_no_body(mock_hh: MockHH) -> None:
    await chats.LEAVE_CHAT(chat_id="5", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/common/chats/5/leave"
    assert dict(request.url.params) == {}
    assert request.content == b""


async def test_mark_chat_message_read_path_params(mock_hh: MockHH) -> None:
    await chats.MARK_CHAT_MESSAGE_READ(chat_id="5", message_id="77", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/common/chats/5/message/77/read"
    assert dict(request.url.params) == {}


async def test_list_chat_messages(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"messages": []}
    await chats.LIST_CHAT_MESSAGES(
        chat_id="5", start_message_id="100", limit=25, order="prev"
    )
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/common/chats/5/messages"
    assert dict(request.url.params) == {
        "start_message_id": "100",
        "limit": "25",
        "order": "prev",
    }


async def test_send_chat_message_text(mock_hh: MockHH) -> None:
    await chats.SEND_CHAT_MESSAGE(chat_id="5", body={"text": "привет"}, confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/common/chats/5/messages"
    assert _json_body(request) == {"text": "привет"}


async def test_send_chat_message_file(mock_hh: MockHH) -> None:
    """Вариант тела с файлом (oneOf-схема) проходит как есть."""
    await chats.SEND_CHAT_MESSAGE(
        chat_id="5", body={"file_upload_id": "8abc"}, confirm=True
    )
    request = mock_hh.requests[-1]
    assert _json_body(request) == {"file_upload_id": "8abc"}


async def test_update_chat_message(mock_hh: MockHH) -> None:
    await chats.UPDATE_CHAT_MESSAGE(
        chat_id="5", message_id="77", body={"text": "исправлено"}, confirm=True
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/common/chats/5/messages/77"
    assert _json_body(request) == {"text": "исправлено"}


async def test_delete_chat_message(mock_hh: MockHH) -> None:
    mock_hh.json_response = None
    result = await chats.DELETE_CHAT_MESSAGE(chat_id="5", message_id="77", confirm=True)
    assert result is None
    request = mock_hh.requests[-1]
    assert request.method == "DELETE"
    assert request.url.path == "/common/chats/5/messages/77"


async def test_get_chat_participants(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"participants": []}
    await chats.GET_CHAT_PARTICIPANTS(chat_id="5")
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/common/chats/5/participants"


async def test_update_chat_participants(mock_hh: MockHH) -> None:
    await chats.UPDATE_CHAT_PARTICIPANTS(chat_id="5", body={"id": "9"}, confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/common/chats/5/participants"
    assert _json_body(request) == {"id": "9"}


async def test_set_chat_write_possibility_query_field(mock_hh: MockHH) -> None:
    """applicant_write_possibility уходит в query, тело – пустое."""
    await chats.SET_CHAT_WRITE_POSSIBILITY(
        chat_id="5", applicant_write_possibility=False, confirm=True
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/common/chats/5/write_possibility"
    assert dict(request.url.params) == {"applicant_write_possibility": "false"}
    assert request.content == b""


@pytest.mark.parametrize(
    ("tool_name", "kwargs"),
    [
        ("create_chat_file_upload_link", {"body": {"file_name": "f.pdf"}}),
        ("create_chat_without_vacancy", {"body": {"resume_hash": "abc"}}),
        ("leave_chat", {"chat_id": "5"}),
        ("mark_chat_message_read", {"chat_id": "5", "message_id": "7"}),
        ("send_chat_message", {"chat_id": "5", "body": {"text": "m"}}),
        ("update_chat_message", {"chat_id": "5", "message_id": "7", "body": {"text": "m"}}),
        ("delete_chat_message", {"chat_id": "5", "message_id": "7"}),
        ("update_chat_participants", {"chat_id": "5", "body": {"id": "9"}}),
        ("set_chat_write_possibility", {"chat_id": "5", "applicant_write_possibility": True}),
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


async def test_write_possibility_query_through_mcp_layer(mock_hh: MockHH) -> None:
    """Через реальный MCP-клиент query-поле и confirm проходят схему инструмента."""
    server = FastMCP(name="test-chats")
    chats.register(server)
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))
    async with Client(server) as client:
        await client.call_tool(
            "set_chat_write_possibility",
            {"chat_id": "5", "applicant_write_possibility": True, "confirm": True},
        )
    request = mock_hh.requests[-1]
    assert request.url.path == "/common/chats/5/write_possibility"
    assert dict(request.url.params) == {"applicant_write_possibility": "true"}


def test_registry_entries_and_flags() -> None:
    entries = REGISTRY.by_toolset("chats")
    assert sorted(e.name for e in entries) == sorted(TOOLS)
    assert len(entries) == 14
    for entry in entries:
        assert entry.requires_auth is True, entry.name
        assert entry.is_mutation == (entry.name not in READ_ONLY), entry.name


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "GET /common/chats",
        "GET /common/chats/counters/unread",
        "GET /common/chats/files/conditions",
        "POST /common/chats/files/upload_links",
        "POST /common/chats/without_vacancy",
        "PUT /common/chats/{chat_id}/leave",
        "PUT /common/chats/{chat_id}/message/{message_id}/read",
        "GET /common/chats/{chat_id}/messages",
        "POST /common/chats/{chat_id}/messages",
        "PUT /common/chats/{chat_id}/messages/{message_id}",
        "DELETE /common/chats/{chat_id}/messages/{message_id}",
        "GET /common/chats/{chat_id}/participants",
        "PUT /common/chats/{chat_id}/participants",
        "PUT /common/chats/{chat_id}/write_possibility",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None
