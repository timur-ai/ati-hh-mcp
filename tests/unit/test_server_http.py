"""In-process тесты HTTP-слоя server.py: гейт, /health, /oauth/callback.

Отличие от tests/mcp_client/test_http.py (подпроцесс e2e): здесь
middleware и маршруты вызываются напрямую через ASGI-транспорт httpx –
строки server.py попадают в покрытие.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from starlette.middleware import Middleware

from ati_hh_mcp import request_context
from ati_hh_mcp import server as server_module
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.hh.token_store import TokenStore, profile_key_from_api_key
from ati_hh_mcp.server import PUBLIC_PATHS, RequestAuthMiddleware, build_http_server

from ..conftest import make_config

Message = dict[str, Any]


def _scope(path: str, headers: dict[str, str]) -> dict[str, Any]:
    """Минимальный http-scope ASGI с заголовками."""
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "headers": [
            (name.encode("latin-1"), value.encode("latin-1"))
            for name, value in headers.items()
        ],
        "query_string": b"",
    }


async def _invoke(
    middleware: RequestAuthMiddleware,
    path: str,
    headers: dict[str, str] | None = None,
) -> list[Message]:
    """Прогоняет запрос через middleware; возвращает отправленные сообщения."""
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await middleware(_scope(path, headers or {}), receive, send)
    return sent


def _inner_app(
    captured: dict[str, Any],
) -> Callable[[dict[str, Any], Any, Any], Awaitable[None]]:
    """Приёмник: фиксирует контекст запроса и отвечает 200."""

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        captured["profile"] = request_context.get_request_profile()
        captured["hh_token"] = request_context.get_request_hh_token()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


@pytest.fixture(autouse=True)
def clean_context() -> None:
    request_context.set_request_auth(hh_token=None, profile=None)


# --- гейт MCP_API_KEYS ------------------------------------------------------


async def test_open_mode_sets_default_profile_and_header_token() -> None:
    """Без ключей сервер открыт; X-HH-Token и default-профиль – в контекст."""
    captured: dict[str, Any] = {}
    middleware = RequestAuthMiddleware(_inner_app(captured), api_keys=())
    sent = await _invoke(middleware, "/mcp", {"X-HH-Token": "tok-1"})
    assert sent[0]["status"] == 200  # запрос прошёл.
    assert captured["profile"] == "default"
    assert captured["hh_token"] == "tok-1"


async def test_valid_api_key_maps_to_sha256_profile() -> None:
    captured: dict[str, Any] = {}
    middleware = RequestAuthMiddleware(_inner_app(captured), api_keys=("key-a",))
    sent = await _invoke(
        middleware, "/mcp", {"Authorization": "Bearer key-a", "X-HH-Token": "tok-2"}
    )
    assert sent[0]["status"] == 200
    assert captured["profile"] == profile_key_from_api_key("key-a")
    assert captured["hh_token"] == "tok-2"


@pytest.mark.parametrize(
    "headers",
    [
        {},  # заголовок отсутствует
        {"Authorization": "Bearer wrong-key"},  # неверный ключ
        {"Authorization": "Basic key-a"},  # не Bearer-схема
        {"Authorization": "Bearer "},  # пустое значение
    ],
    ids=["missing", "wrong-key", "not-bearer", "empty-value"],
)
async def test_unauthorized_rejected_with_json_401(headers: dict[str, str]) -> None:
    captured: dict[str, Any] = {}
    middleware = RequestAuthMiddleware(_inner_app(captured), api_keys=("key-a",))
    sent = await _invoke(middleware, "/mcp", headers)
    assert sent[0]["status"] == 401
    content_type = dict(sent[0]["headers"])[b"content-type"]
    assert b"application/json" in content_type
    body = json.loads(sent[1]["body"])
    assert body["error"]["code"] == "unauthorized"
    assert "API-ключ" in body["error"]["description"]
    assert captured == {}  # внутреннее приложение не вызывалось.


async def test_public_paths_bypass_gate_and_context() -> None:
    """/health и /oauth/callback доступны без ключей, контекст не трогается."""
    captured: dict[str, Any] = {}
    middleware = RequestAuthMiddleware(_inner_app(captured), api_keys=("key-a",))
    for path in sorted(PUBLIC_PATHS):
        sent = await _invoke(middleware, path)
        assert sent[0]["status"] == 200, path
    # Приложение вызвано, но middleware не задавал контекст запроса.
    assert captured == {"profile": None, "hh_token": None}


async def test_non_http_scope_passes_through() -> None:
    """lifespan-сообщения ASGI идут напрямую (не http-запросы)."""
    captured: dict[str, Any] = {}

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        captured["type"] = scope["type"]

    middleware = RequestAuthMiddleware(app, api_keys=("key-a",))

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        captured.setdefault("sent", []).append(message)

    await middleware({"type": "lifespan"}, receive, send)
    assert captured["type"] == "lifespan"


# --- маршруты /health и /oauth/callback --------------------------------------


@pytest.fixture
def http_app(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> httpx.ASGITransport:
    """HTTP-приложение сервера с временным хранилищем токенов."""
    monkeypatch.setenv("HH_TOKEN_STORE", str(tmp_path / "tokens.sqlite3"))
    fastmcp_server = build_http_server(make_config(toolsets=("auth",)))
    app = fastmcp_server.http_app(
        middleware=[Middleware(RequestAuthMiddleware, api_keys=())]
    )
    return httpx.ASGITransport(app=app)


def _store_path() -> str:
    """Путь к базе токенов, зафиксированный фикстурой http_app."""
    return os.environ["HH_TOKEN_STORE"]


async def test_health_route_json(http_app: httpx.ASGITransport) -> None:
    async with httpx.AsyncClient(transport=http_app, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"]


async def test_oauth_callback_requires_code_and_state(http_app: httpx.ASGITransport) -> None:
    async with httpx.AsyncClient(transport=http_app, base_url="http://test") as client:
        response = await client.get("/oauth/callback")
    assert response.status_code == 400
    assert "code" in response.text


async def test_oauth_callback_rejects_forged_state(http_app: httpx.ASGITransport) -> None:
    async with httpx.AsyncClient(transport=http_app, base_url="http://test") as client:
        response = await client.get(
            "/oauth/callback", params={"code": "c", "state": "forged.deadbeef"}
        )
    assert response.status_code == 400
    assert "state" in response.text


async def test_oauth_callback_success_saves_tokens(
    http_app: httpx.ASGITransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Валидный state -> exchange_code -> токены в профиль из state."""
    exchanged: list[str] = []

    class FakeOAuth:
        def __init__(self, config: Any, store: TokenStore) -> None:
            self._store = store

        async def exchange_code(self, code: str, profile: str) -> Any:
            exchanged.append(code)
            return self._store.save_tokens(profile, f"AT-{code}", None)

    monkeypatch.setattr(server_module, "HHOAuth", FakeOAuth)

    store = TokenStore(_store_path())
    try:
        state = store.sign_state("default")
    finally:
        store.close()

    async with httpx.AsyncClient(transport=http_app, base_url="http://test") as client:
        response = await client.get(
            "/oauth/callback", params={"code": "abc", "state": state}
        )
    assert response.status_code == 200
    assert "сохранены" in response.text
    assert exchanged == ["abc"]

    saved = TokenStore(_store_path())
    try:
        tokens = saved.get_tokens("default")
    finally:
        saved.close()
    assert tokens is not None
    assert tokens.access_token == "AT-abc"


async def test_oauth_callback_exchange_failure_502(
    http_app: httpx.ASGITransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    """hh.ru отклонил обмен кода – человекочитаемая ошибка 502."""

    class FailingOAuth:
        def __init__(self, config: Any, store: TokenStore) -> None: ...

        async def exchange_code(self, code: str, profile: str) -> Any:
            raise HHError("oauth_bad_response", "hh.ru отклонил код.")

    monkeypatch.setattr(server_module, "HHOAuth", FailingOAuth)

    store = TokenStore(_store_path())
    try:
        state = store.sign_state("default")
    finally:
        store.close()

    async with httpx.AsyncClient(transport=http_app, base_url="http://test") as client:
        response = await client.get(
            "/oauth/callback", params={"code": "abc", "state": state}
        )
    assert response.status_code == 502
    assert "отклонил" in response.text

