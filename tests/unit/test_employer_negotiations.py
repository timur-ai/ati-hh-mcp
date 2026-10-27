"""Тесты набора инструментов «employer_negotiations» против MockTransport."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets.employer_negotiations import (
    EMPLOYER_GET_MANAGER_NEGOTIATIONS_STATISTICS,
    EMPLOYER_GET_NEGOTIATIONS_STATISTICS,
    EMPLOYER_GET_RESUME_NEGOTIATIONS_HISTORY,
    EMPLOYER_LIST_MAIL_TEMPLATES,
    EMPLOYER_UPDATE_MAIL_TEMPLATE,
    register,
)

from ..conftest import MockHH, make_config

TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "employer_list_mail_templates": EMPLOYER_LIST_MAIL_TEMPLATES,
    "employer_update_mail_template": EMPLOYER_UPDATE_MAIL_TEMPLATE,
    "employer_get_resume_negotiations_history": EMPLOYER_GET_RESUME_NEGOTIATIONS_HISTORY,
    "employer_get_negotiations_statistics": EMPLOYER_GET_NEGOTIATIONS_STATISTICS,
    "employer_get_manager_negotiations_statistics": EMPLOYER_GET_MANAGER_NEGOTIATIONS_STATISTICS,
}


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


async def test_list_mail_templates(mock_hh: MockHH) -> None:
    mock_hh.json_response = [{"id": "invite_mail", "name": "Приглашение"}]
    result = await EMPLOYER_LIST_MAIL_TEMPLATES(employer_id="777")
    assert result[0]["id"] == "invite_mail"
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/employers/777/mail_templates"
    assert dict(request.url.params) == {}  # employer_id ушёл в путь, не в query.


async def test_update_mail_template_body_and_confirm(mock_hh: MockHH) -> None:
    template = {"text": "Здравствуйте, [Name]! Ждём вас на интервью."}

    # Без confirm – структурированная ошибка, HTTP не выполняется.
    with pytest.raises(HHError) as excinfo:
        await EMPLOYER_UPDATE_MAIL_TEMPLATE(
            employer_id="777", template_id="invite_mail", body=template
        )
    assert excinfo.value.code == "confirm_required"
    assert mock_hh.requests == []

    await EMPLOYER_UPDATE_MAIL_TEMPLATE(
        employer_id="777", template_id="invite_mail", body=template, confirm=True
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/employers/777/mail_templates/invite_mail"
    # Оба path-параметра подставлены, тело – JSON со схемой шаблона.
    assert dict(request.url.params) == {}
    assert json.loads(request.read()) == template


async def test_get_resume_negotiations_history(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_GET_RESUME_NEGOTIATIONS_HISTORY(resume_id="0123456789abcdef")
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/resumes/0123456789abcdef/negotiations_history"
    assert dict(request.url.params) == {}


async def test_get_negotiations_statistics(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"total": 10}
    result = await EMPLOYER_GET_NEGOTIATIONS_STATISTICS(employer_id="777")
    assert result["total"] == 10
    request = mock_hh.requests[-1]
    assert request.url.path == "/employers/777/negotiations_statistics"


async def test_get_manager_negotiations_statistics_two_path_params(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"total": 3}
    result = await EMPLOYER_GET_MANAGER_NEGOTIATIONS_STATISTICS(employer_id="777", manager_id="5")
    assert result["total"] == 3
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/employers/777/managers/5/negotiations_statistics"
    assert dict(request.url.params) == {}


async def test_register_lists_all_tools_on_server(mock_hh: MockHH) -> None:
    """register() подключает все 5 инструментов (контракт волны 2)."""
    server = FastMCP(name="test-employer-negotiations")
    register(server, lambda: HHClient(make_config(), transport=mock_hh.transport))
    async with Client(server) as client:
        tools = await client.list_tools()
    assert {tool.name for tool in tools} == set(TOOLS)


def test_registry_entries_and_flags() -> None:
    entries = REGISTRY.by_toolset("employer_negotiations")
    assert len(entries) == 5
    assert sorted(e.name for e in entries) == sorted(TOOLS)
    for entry in entries:
        assert entry.requires_auth is True, entry.name
        method = entry.operation_id.split(" ", 1)[0]
        assert entry.is_mutation is (method != "GET"), entry.name


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "GET /employers/{employer_id}/mail_templates",
        "PUT /employers/{employer_id}/mail_templates/{template_id}",
        "GET /resumes/{resume_id}/negotiations_history",
        "GET /employers/{employer_id}/negotiations_statistics",
        "GET /employers/{employer_id}/managers/{manager_id}/negotiations_statistics",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None
