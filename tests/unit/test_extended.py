"""Тесты extended-набора (недокументированные операции) на моках."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets import extended

from ..conftest import make_config

EXTENDED_TOOLS = {
    "apply_to_vacancy",
    "my_resumes",
    "artifacts_list",
    "artifact_delete",
}


class ExtendedMock:
    """Транспорт extended-операций с настройкой ответа POST /negotiations."""

    def __init__(
        self,
        *,
        apply_status: int = 201,
        apply_location: str = "/negotiations/123",
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.apply_status = apply_status
        self.apply_location = apply_location

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST" and path == "/negotiations":
            headers = {"Location": self.apply_location} if self.apply_location else {}
            # 201 Created от hh.ru несёт только заголовок Location (без тела);
            # 303 тоже без тела.
            body = {"url": self.apply_location} if self.apply_status == 409 else None
            return httpx.Response(self.apply_status, headers=headers, json=body)
        if request.method == "GET" and path == "/resumes/mine":
            return httpx.Response(200, json={"items": [{"id": "RES-1"}], "found": 1})
        if request.method == "GET" and path in ("/artifacts/photo", "/artifacts/portfolio"):
            return httpx.Response(200, json={"items": [{"id": "92278992"}], "found": 1})
        if request.method == "DELETE" and path.startswith("/artifacts/"):
            return httpx.Response(204)
        return httpx.Response(404, json={"errors": [{"type": "not_found"}]})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def mock() -> ExtendedMock:
    return ExtendedMock()


@pytest.fixture
async def client(mock: ExtendedMock) -> Any:
    config = make_config(token="APPLICANT-TOKEN")
    server = FastMCP(name="extended-test")
    extended.register(server, lambda: HHClient(config, transport=mock.transport))
    async with Client(server) as mcp_client:
        yield mcp_client


# ----------------------------------------------------------------------
# Состав и реестр
# ----------------------------------------------------------------------
async def test_all_four_tools_listed(client: Client) -> None:
    tools = await client.list_tools()
    assert {tool.name for tool in tools} == EXTENDED_TOOLS


def test_registry_flags_undocumented() -> None:
    expectations = {
        "apply_to_vacancy": ("POST /negotiations", True),
        "my_resumes": ("GET /resumes/mine", False),
        "artifacts_list": ("GET /artifacts/{artifact_type}", False),
        "artifact_delete": ("DELETE /artifacts/{artifact_id}", True),
    }
    for name, (operation_id, is_mutation) in expectations.items():
        entry = REGISTRY.get(name)
        assert entry is not None, name
        assert entry.toolset == "extended"
        assert entry.operation_id == operation_id
        assert entry.is_mutation is is_mutation
        assert entry.requires_auth is True
        assert entry.undocumented is True, name


# ----------------------------------------------------------------------
# apply_to_vacancy
# ----------------------------------------------------------------------
async def test_apply_requires_confirm(client: Client, mock: ExtendedMock) -> None:
    with pytest.raises(Exception, match="confirm_required"):
        await client.call_tool(
            "apply_to_vacancy",
            {"vacancy_id": "VAC-1", "resume_id": "RES-1"},
        )
    assert mock.requests == []


async def test_apply_sends_multipart_form(client: Client, mock: ExtendedMock) -> None:
    result = await client.call_tool(
        "apply_to_vacancy",
        {
            "vacancy_id": "VAC-1",
            "resume_id": "RES-1",
            "message": "Здравствуйте!",
            "confirm": True,
        },
    )
    assert result.data == {"created": True, "location": "/negotiations/123"}

    request = mock.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/negotiations"
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert b"vacancy_id" in body and b"VAC-1" in body
    assert b"resume_id" in body and b"RES-1" in body
    assert b"message" in body and "Здравствуйте!".encode() in body


async def test_apply_without_message(client: Client, mock: ExtendedMock) -> None:
    await client.call_tool(
        "apply_to_vacancy",
        {"vacancy_id": "VAC-1", "resume_id": "RES-1", "confirm": True},
    )
    body = mock.requests[0].content
    assert b"vacancy_id" in body
    assert b"message" not in body


async def test_apply_direct_vacancy_returns_redirect(
    mock: ExtendedMock,
) -> None:
    mock.apply_status = 303
    mock.apply_location = "https://example.test/respond"
    config = make_config(token="APPLICANT-TOKEN")
    server = FastMCP(name="extended-direct")
    extended.register(server, lambda: HHClient(config, transport=mock.transport))
    async with Client(server) as mcp_client:
        result = await mcp_client.call_tool(
            "apply_to_vacancy",
            {"vacancy_id": "VAC-1", "resume_id": "RES-1", "confirm": True},
        )
    assert result.data["created"] is False
    assert result.data["redirect_url"] == "https://example.test/respond"


async def test_apply_error_passthrough(client: Client, mock: ExtendedMock) -> None:
    mock.apply_status = 409
    mock.apply_location = None
    with pytest.raises(Exception, match="conflict"):
        await client.call_tool(
            "apply_to_vacancy",
            {"vacancy_id": "VAC-1", "resume_id": "RES-1", "confirm": True},
        )


# ----------------------------------------------------------------------
# my_resumes / artifacts
# ----------------------------------------------------------------------
async def test_my_resumes_requests_path(client: Client, mock: ExtendedMock) -> None:
    result = await client.call_tool("my_resumes", {})
    assert result.data == {"items": [{"id": "RES-1"}], "found": 1}
    request = mock.requests[0]
    assert request.method == "GET"
    assert request.url.path == "/resumes/mine"
    assert request.headers["authorization"] == "Bearer APPLICANT-TOKEN"


async def test_artifacts_list_default_photo(client: Client, mock: ExtendedMock) -> None:
    result = await client.call_tool("artifacts_list", {})
    assert result.data == {"items": [{"id": "92278992"}], "found": 1}
    assert mock.requests[0].url.path == "/artifacts/photo"


async def test_artifacts_list_portfolio(client: Client, mock: ExtendedMock) -> None:
    await client.call_tool("artifacts_list", {"artifact_type": "portfolio"})
    assert mock.requests[0].url.path == "/artifacts/portfolio"


async def test_artifacts_list_rejects_unknown_type(client: Client) -> None:
    # Значение вне enum отсекается слоем валидации MCP до вызова инструмента.
    with pytest.raises(ToolError, match="photo.*portfolio|literal_error"):
        await client.call_tool("artifacts_list", {"artifact_type": "video"})


# ----------------------------------------------------------------------
# artifact_delete
# ----------------------------------------------------------------------
async def test_artifact_delete_requires_confirm(
    client: Client,
    mock: ExtendedMock,
) -> None:
    with pytest.raises(Exception, match="confirm_required"):
        await client.call_tool("artifact_delete", {"artifact_id": "92278992"})
    assert mock.requests == []


async def test_artifact_delete_requests_delete(
    client: Client,
    mock: ExtendedMock,
) -> None:
    result = await client.call_tool(
        "artifact_delete", {"artifact_id": "92278992", "confirm": True}
    )
    assert result.data == {"deleted": True, "artifact_id": "92278992"}
    request = mock.requests[0]
    assert request.method == "DELETE"
    assert request.url.path == "/artifacts/92278992"
