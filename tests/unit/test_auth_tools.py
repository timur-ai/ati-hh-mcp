"""Тесты набора «auth» на in-memory FastMCP + моки httpx.

Сценарий полностью повторяет stdio-путь OAuth: auth_get_login_url ->
auth_exchange_code -> get_me (включая 401 -> refresh -> повтор) ->
auth_status -> auth_logout.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastmcp import Client, FastMCP

from ati_hh_mcp import request_context
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.token_store import TokenStore, profile_key_from_api_key
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets import auth_tools

from ..conftest import make_config

AUTH_TOOLS = {
    "get_me",
    "auth_get_login_url",
    "auth_exchange_code",
    "auth_status",
    "auth_logout",
}


class AuthFlowMock:
    """Транспорт OAuth-сценария: POST/DELETE /token + GET /me.

    GET /me отвечает 200 только для Bearer-токенов из ``valid_tokens``;
    POST /token выдаёт новую пару (по счётчику обмена).
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.valid_tokens = {"AT1"}
        self.exchange_count = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST" and path == "/token":
            self.exchange_count += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"AT{self.exchange_count}",
                    "refresh_token": f"RT{self.exchange_count}",
                    "token_type": "bearer",
                },
            )
        if request.method == "DELETE" and path == "/token":
            return httpx.Response(204)
        if request.method == "GET" and path == "/me":
            authorization = request.headers.get("authorization", "")
            token = authorization.removeprefix("Bearer ").strip()
            if token in self.valid_tokens:
                return httpx.Response(200, json={"id": "42", "is_applicant": True})
            return httpx.Response(
                401,
                json={"errors": [{"type": "oauth", "value": "bad_authorization"}]},
            )
        return httpx.Response(404, json={"errors": [{"type": "not_found"}]})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def store() -> Iterator[TokenStore]:
    token_store = TokenStore()
    yield token_store
    token_store.close()


@pytest.fixture
def mock() -> AuthFlowMock:
    return AuthFlowMock()


@pytest.fixture
def config():
    return make_config(
        client_id="CID",
        client_secret="SECRET",
        redirect_uri="https://example.test/cb",
    )


@pytest.fixture
async def client(
    store: TokenStore,
    mock: AuthFlowMock,
    config: Any,
) -> Iterator[Client]:
    """In-memory MCP-клиент против мини-сервера с набором auth."""
    server = FastMCP(name="auth-test")
    auth_tools.register(
        server,
        lambda: HHClient(config, transport=mock.transport),
        config=config,
        store=store,
        transport=mock.transport,
    )
    async with Client(server) as mcp_client:
        yield mcp_client


# ----------------------------------------------------------------------
# Состав и реестр
# ----------------------------------------------------------------------
async def test_all_five_tools_listed(client: Client) -> None:
    tools = await client.list_tools()
    assert {tool.name for tool in tools} == AUTH_TOOLS


def test_registry_entries() -> None:
    get_me = REGISTRY.get("get_me")
    assert get_me is not None
    assert get_me.operation_id == "GET /me"
    assert get_me.toolset == "auth"
    assert get_me.requires_auth is True
    assert get_me.is_mutation is False

    logout = REGISTRY.get("auth_logout")
    assert logout is not None
    assert logout.operation_id == "DELETE /token"
    assert logout.is_mutation is True

    service_operations = {
        "auth_get_login_url": "INTERNAL auth:login_url",
        "auth_exchange_code": "INTERNAL auth:exchange_code",
        "auth_status": "INTERNAL auth:status",
    }
    for name, operation_id in service_operations.items():
        entry = REGISTRY.get(name)
        assert entry is not None, name
        assert entry.operation_id == operation_id


# ----------------------------------------------------------------------
# auth_get_login_url
# ----------------------------------------------------------------------
async def test_get_login_url_returns_url_and_instructions(client: Client) -> None:
    result = await client.call_tool("auth_get_login_url", {})
    payload = result.data
    assert isinstance(payload, dict)
    query = parse_qs(urlparse(payload["url"]).query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["CID"]
    assert query["state"][0].startswith("default|")
    assert "auth_exchange_code" in payload["instructions"]
    assert "hh.ru" in payload["instructions"]


async def test_get_login_url_without_client_id(
    store: TokenStore,
    mock: AuthFlowMock,
) -> None:
    server = FastMCP(name="auth-test-nocreds")
    no_creds = make_config(client_id=None, client_secret=None)
    auth_tools.register(
        server,
        lambda: HHClient(no_creds, transport=mock.transport),
        config=no_creds,
        store=store,
        transport=mock.transport,
    )
    async with Client(server) as mcp_client:
        with pytest.raises(Exception, match="oauth_not_configured"):
            await mcp_client.call_tool("auth_get_login_url", {})
    assert mock.requests == []


# ----------------------------------------------------------------------
# Полный сценарий: login_url -> exchange -> get_me (401 -> refresh) -> logout
# ----------------------------------------------------------------------
async def test_full_oauth_scenario(
    client: Client,
    store: TokenStore,
    mock: AuthFlowMock,
) -> None:
    # 1. Обмен кода сохраняет пару токенов.
    exchange = await client.call_tool("auth_exchange_code", {"code": "CODE-1"})
    assert isinstance(exchange.data, dict)
    assert exchange.data["ok"] is True
    assert store.get_tokens("default").access_token == "AT1"
    token_request = next(
        r for r in mock.requests if r.url.path == "/token" and r.method == "POST"
    )
    body = parse_qs(token_request.content.decode("utf-8"))
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["CODE-1"]

    # 2. get_me: токен AT1 недействителен -> 401 -> refresh -> AT2 -> успех.
    mock.valid_tokens = {"AT2"}
    me = await client.call_tool("get_me", {})
    assert me.data == {"id": "42", "is_applicant": True}
    assert store.get_tokens("default").access_token == "AT2"
    refresh_request = [
        r for r in mock.requests if r.url.path == "/token" and r.method == "POST"
    ][-1]
    refresh_body = parse_qs(refresh_request.content.decode("utf-8"))
    assert refresh_body["grant_type"] == ["refresh_token"]
    assert refresh_body["refresh_token"] == ["RT1"]

    # 3. auth_status видит сохранённые токены.
    status = await client.call_tool("auth_status", {})
    assert status.data == {
        "configured": True,
        "has_tokens": True,
        "profile": "default",
        "obtained_at": store.get_tokens("default").obtained_at,
    }

    # 4. logout отзывает токен и удаляет профиль.
    logout = await client.call_tool("auth_logout", {"confirm": True})
    assert isinstance(logout.data, dict)
    assert logout.data["revoked"] is True
    delete_request = next(
        r for r in mock.requests if r.method == "DELETE" and r.url.path == "/token"
    )
    assert delete_request.headers["authorization"] == "Bearer AT2"
    assert store.get_tokens("default") is None


async def test_status_before_exchange(client: Client) -> None:
    status = await client.call_tool("auth_status", {})
    assert status.data == {
        "configured": True,
        "has_tokens": False,
        "profile": "default",
        "obtained_at": None,
    }


async def test_status_shows_request_profile(client: Client, store: TokenStore) -> None:
    """HTTP-режим: auth_status показывает профиль запроса (sha256 ключа)."""
    profile = profile_key_from_api_key("key-a")
    store.save_tokens(profile, "AT-x", "RT-x")
    try:
        request_context.set_request_auth(hh_token=None, profile=profile)
        status = await client.call_tool("auth_status", {})
    finally:
        request_context.set_request_auth(hh_token=None, profile=None)
    assert status.data["profile"] == profile
    assert status.data["has_tokens"] is True
    assert status.data["obtained_at"] == store.get_tokens(profile).obtained_at


# ----------------------------------------------------------------------
# get_me без токена и confirm-семантика logout
# ----------------------------------------------------------------------
async def test_get_me_without_token_raises_russian_error(
    store: TokenStore,
    mock: AuthFlowMock,
    config: Any,
) -> None:
    server = FastMCP(name="auth-test-notoken")
    auth_tools.register(server, lambda: HHClient(config), config=config, store=store)
    async with Client(server) as mcp_client:
        with pytest.raises(Exception, match="no_hh_token"):
            await mcp_client.call_tool("get_me", {})
    assert mock.requests == []


async def test_logout_requires_confirm(client: Client) -> None:
    with pytest.raises(Exception, match="confirm_required"):
        await client.call_tool("auth_logout", {})


async def test_get_me_uses_env_token_when_no_profile(
    mock: AuthFlowMock,
    store: TokenStore,
) -> None:
    """Env-токен HH_TOKEN применяется для default-профиля."""
    mock.valid_tokens = {"ENV-AT"}
    env_config = make_config(
        token="ENV-AT",
        client_id="CID",
        client_secret="SECRET",
        redirect_uri="https://example.test/cb",
    )
    server = FastMCP(name="auth-test-env")
    auth_tools.register(
        server,
        lambda: HHClient(env_config, transport=mock.transport),
        config=env_config,
        store=store,
        transport=mock.transport,
    )
    async with Client(server) as mcp_client:
        me = await mcp_client.call_tool("get_me", {})
    assert me.data == {"id": "42", "is_applicant": True}
