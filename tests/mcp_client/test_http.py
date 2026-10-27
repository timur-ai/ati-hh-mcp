"""E2E: реальный MCP-клиент против HTTP-сервера (подпроцесс, этап M7).

Сценарии:
- подпроцесс ``ati-hh-mcp serve --transport http`` на случайном свободном
  порту, ожидание готовности через ``/health``;
- tools/list по streamable-http (дефолтные наборы, без employer_*);
- вызов инструмента против стаба API hh.ru (stdlib http.server) с
  проверкой пути и заголовка Authorization;
- гейт ``MCP_API_KEYS``: без/неверный ключ – 401 JSON, верный – работает,
  ``/health`` остаётся открытым;
- сквозная передача ``X-HH-Token`` в заголовок hh-запроса.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from ati_hh_mcp.hh.token_store import TokenStore

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Дефолтные наборы: auth(5) + dictionaries(16) + suggests(11) + vacancies(4)
#: + negotiations(10) + chats(14) + resumes(2).
EXPECTED_DEFAULT_TOOLS = 62

_TMP_STORE_DIR = Path(tempfile.mkdtemp(prefix="ati-hh-mcp-http-"))

#: Устойчивое к переходным ошибкам время ожидания готовности подпроцесса.
STARTUP_TIMEOUT = 90.0


def _free_port() -> int:
    """Случайный свободный порт на 127.0.0.1."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class StubHH:
    """Стаб API hh.ru на stdlib http.server: JSON на любой GET.

    Запоминает путь и заголовки последнего запроса (проверка
    пробрасывания Authorization), тело ответа настраивается полем
    ``response``.
    """

    def __init__(self) -> None:
        self.port = _free_port()
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.posts: list[tuple[str, str]] = []
        self.response: dict[str, object] = {"currency": {"RUR": {"code": "RUR"}}}
        #: Ответ стаба на POST /token (OAuth-обмен).
        self.post_response: dict[str, object] = {
            "access_token": "stub-access",
            "refresh_token": "stub-refresh",
        }
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                stub.requests.append((self.path, {k: v for k, v in self.headers.items()}))
                body = json.dumps(stub.response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                form = self.rfile.read(length).decode("utf-8")
                stub.posts.append((self.path, form))
                body = json.dumps(stub.post_response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: object) -> None:  # тишина в выводе pytest
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class HttpMCPServer:
    """Подпроцесс HTTP-сервера на свободном порту; готовность – /health."""

    def __init__(self, env_extra: dict[str, str] | None = None) -> None:
        self.port = _free_port()
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("HH_", "MCP_"))
        }
        self.store_path = _TMP_STORE_DIR / f"tokens-{self.port}.sqlite3"
        env["HH_TOKEN_STORE"] = str(self.store_path)
        env.setdefault("HH_UA_EMAIL", "owner@example.test")
        env.update(env_extra or {})
        self.proc = subprocess.Popen(  # noqa: S603 - команда фиксирована внутри проекта
            [
                "uv",
                "run",
                "python",
                "-m",
                "ati_hh_mcp",
                "serve",
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_until_ready()

    def _wait_until_ready(self, timeout: float = STARTUP_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"HTTP-подпроцесс завершился досрочно (код {self.proc.returncode})"
                )
            try:
                response = httpx.get(f"{self.url}/health", timeout=2.0)
                if response.status_code == 200:
                    return
            except httpx.HTTPError as error:  # сервер ещё поднимается
                last_error = error
            time.sleep(0.3)
        raise TimeoutError(f"сервер не поднялся за {timeout} с: {last_error}")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def mcp_url(self) -> str:
        return f"{self.url}/mcp"

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)


def _client(mcp_url: str, headers: dict[str, str] | None = None) -> Client:
    return Client(StreamableHttpTransport(url=mcp_url, headers=headers))


@pytest.fixture
def stub_hh() -> Iterator[StubHH]:
    stub = StubHH()
    yield stub
    stub.close()


async def test_health_and_default_tools_list() -> None:
    """(а, д) /health 200 с версией; tools/list – 62 дефолтных, без employer_*."""
    server = HttpMCPServer()
    try:
        response = httpx.get(f"{server.url}/health", timeout=10.0)
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["version"]

        async with _client(server.mcp_url) as client:
            tools = await client.list_tools()
        names = {tool.name for tool in tools}
        assert len(names) == EXPECTED_DEFAULT_TOOLS
        assert not any(name.startswith("employer_") for name in names)
        assert {"auth_status", "dict_dictionaries", "list_negotiations"} <= names
    finally:
        server.stop()


async def test_call_dict_tool_against_stub_hh(stub_hh: StubHH) -> None:
    """(б) вызов инструмента уходит на стаб hh.ru и возвращается JSON."""
    server = HttpMCPServer({"HH_API_BASE": stub_hh.url})
    try:
        async with _client(server.mcp_url) as client:
            result = await client.call_tool("dict_dictionaries", {})
        assert result.data == stub_hh.response
        path, _headers = stub_hh.requests[-1]
        assert path == "/dictionaries"
    finally:
        server.stop()


async def test_api_key_gate(stub_hh: StubHH) -> None:
    """(в) без ключа и с неверным – 401 JSON; с верным – работает."""
    server = HttpMCPServer(
        {"MCP_API_KEYS": "key-one,key-two", "HH_API_BASE": stub_hh.url}
    )
    try:
        missing = httpx.get(server.mcp_url, timeout=10.0)
        assert missing.status_code == 401
        assert missing.json()["error"]["code"] == "unauthorized"
        assert "API-ключ" in missing.json()["error"]["description"]

        wrong = httpx.get(
            server.mcp_url,
            headers={"Authorization": "Bearer wrong-key"},
            timeout=10.0,
        )
        assert wrong.status_code == 401
        assert wrong.json()["error"]["code"] == "unauthorized"

        # /health остаётся открытым без авторизации.
        assert httpx.get(f"{server.url}/health", timeout=10.0).status_code == 200

        transport = StreamableHttpTransport(
            url=server.mcp_url, headers={"Authorization": "Bearer key-two"}
        )
        async with Client(transport) as client:
            tools = await client.list_tools()
        assert {tool.name for tool in tools} >= {"dict_dictionaries", "auth_status"}
    finally:
        server.stop()


async def test_xhh_token_passed_to_hh_api(stub_hh: StubHH) -> None:
    """(г) X-HH-Token запроса уходит в Authorization Bearer к API hh.ru."""
    stub_hh.response = {"id": "42", "email": "user@example.test"}
    server = HttpMCPServer({"HH_API_BASE": stub_hh.url})
    try:
        transport = StreamableHttpTransport(
            url=server.mcp_url, headers={"X-HH-Token": "hh-token-e2e"}
        )
        async with Client(transport) as client:
            result = await client.call_tool("get_me", {})
        assert result.data["id"] == "42"
        path, headers = stub_hh.requests[-1]
        assert path == "/me"
        assert headers.get("Authorization") == "Bearer hh-token-e2e"
    finally:
        server.stop()


async def test_oauth_callback_exchanges_code(stub_hh: StubHH) -> None:
    """/oauth/callback: проверка state, обмен кода, человекочитаемый ответ."""
    server = HttpMCPServer(
        {
            "HH_API_BASE": stub_hh.url,
            "HH_CLIENT_ID": "stub-client",
            "HH_CLIENT_SECRET": "stub-secret",
            "HH_REDIRECT_URI": "http://localhost/oauth/callback",
        }
    )
    try:
        # state подписываем тем же файлом SQLite, что и сервер.
        signing_store = TokenStore(server.store_path)
        try:
            state = signing_store.sign_state("default")
        finally:
            signing_store.close()

        ok = httpx.get(
            f"{server.url}/oauth/callback",
            params={"code": "abc", "state": state},
            timeout=10.0,
        )
        assert ok.status_code == 200
        assert "сохранены" in ok.text  # человекочитаемый ответ об успехе.

        # Код ушли на обмен POST /token (form-encoded, grant_type authorization_code).
        path, form = stub_hh.posts[-1]
        assert path == "/token"
        assert "grant_type=authorization_code" in form
        assert "code=abc" in form

        # Пара токенов записана в профиль default серверного store.
        server_store = TokenStore(server.store_path)
        try:
            tokens = server_store.get_tokens("default")
        finally:
            server_store.close()
        assert tokens is not None
        assert tokens.access_token == "stub-access"

        # Подделанный state и отсутствие параметров – человекочитаемая ошибка.
        bad = httpx.get(
            f"{server.url}/oauth/callback",
            params={"code": "abc", "state": "forged.deadbeef"},
            timeout=10.0,
        )
        assert bad.status_code == 400
        assert "state" in bad.text
        missing = httpx.get(f"{server.url}/oauth/callback", timeout=10.0)
        assert missing.status_code == 400
    finally:
        server.stop()
