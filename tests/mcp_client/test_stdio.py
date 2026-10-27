"""E2E: реальный MCP-клиент против stdio-сервера.

Два сценария:
- in-memory: клиент fastmcp к собранному серверу с подставленным транспортом;
- subprocess: настоящий процесс `python -m ati_hh_mcp serve --transport stdio`
  плюс проверка инварианта «stdout содержит только протокол MCP».
"""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.server import build_server

from ..conftest import MockHH, make_config

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DICT_TOOLS = {"dict_dictionaries", "dict_areas", "dict_metro"}

# Временный каталог для SQLite-базы токенов подпроцессов (не HOME).
_TMP_STORE_DIR = Path(tempfile.mkdtemp(prefix="ati-hh-mcp-e2e-"))


async def test_inmemory_client_lists_and_calls_tools(mock_hh: MockHH) -> None:
    """Клиент в памяти: initialize, tools/list, вызов справочника."""
    mock_hh.json_response = {"currency": {"RUR": {"code": "RUR", "abbr": "руб."}}}
    config = make_config()
    server = build_server(config)
    # Подставляем транспорт после сборки сервера.
    toolkit.set_client_factory(lambda: HHClient(config, transport=mock_hh.transport))

    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        assert names >= DICT_TOOLS

        result = await client.call_tool("dict_dictionaries", {})
        assert result.data == mock_hh.json_response
        assert mock_hh.requests[0].url.path == "/dictionaries"


def _server_command() -> list[str]:
    """Команда запуска сервера: uv run (как в README) с фолбэком на sys.executable."""
    if shutil.which("uv"):
        return ["uv", "run", "python", "-m", "ati_hh_mcp", "serve", "--transport", "stdio"]
    return [sys.executable, "-m", "ati_hh_mcp", "serve", "--transport", "stdio"]


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Окружение без переменных проекта (детерминированный запуск).

    ``extra`` добавляется поверх (например, HH_TOOLSETS=extended);
    HH_TOKEN_STORE всегда уводится во временный каталог, чтобы запуск
    сервера с auth-набором не создавал базу токенов в HOME.
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("HH_", "MCP_"))
    }
    env["HH_TOKEN_STORE"] = str(_TMP_STORE_DIR / "tokens.sqlite3")
    if extra:
        env.update(extra)
    return env


async def test_subprocess_client_stdio_initialize_and_list() -> None:
    """Реальный подпроцесс: MCP-клиент по stdio, initialize + tools/list."""
    transport = StdioTransport(
        command=_server_command()[0],
        args=_server_command()[1:],
        cwd=PROJECT_ROOT,
        env=_clean_env(),
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        assert names >= DICT_TOOLS


def _read_stdout_lines(proc: subprocess.Popen[str], count: int, timeout: float) -> list[str]:
    """Читает строки stdout с таймаутом на каждую (без блокировки навсегда)."""
    lines: list[str] = []
    deadline = time.monotonic() + timeout
    fd = proc.stdout.fileno()  # type: ignore[union-attr]
    while len(lines) < count and time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], max(0.0, deadline - time.monotonic()))
        if not ready:
            break
        line = proc.stdout.readline()  # type: ignore[union-attr]
        if not line:
            break
        lines.append(line)
    return lines


def test_subprocess_stdout_contains_only_mcp_protocol() -> None:
    """Инвариант: в stdout подпроцесса – только JSON-строки протокола MCP."""
    proc = subprocess.Popen(  # noqa: S603 - команда фиксирована внутри проекта
        _server_command(),
        cwd=PROJECT_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_clean_env(),
    )
    try:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "purity-test", "version": "0.0.0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        for request in requests:
            proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()

        # initialize + initialized(нет ответа) + tools/list -> ждём 2 ответа.
        lines = _read_stdout_lines(proc, count=2, timeout=20.0)
        assert len(lines) == 2, f"ожидались 2 строки протокола, получено: {lines!r}"

        parsed: list[dict] = []
        for line in lines:
            # Инвариант: каждая строка stdout – валидный JSON (протокол MCP).
            parsed.append(json.loads(line))

        by_id = {message.get("id"): message for message in parsed}
        initialize_result = by_id[1]["result"]
        assert initialize_result["serverInfo"]["name"] == "ati-hh-mcp"
        tool_names = {
            tool["name"] for tool in by_id[2]["result"]["tools"]
        }
        assert tool_names >= DICT_TOOLS
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        # Логи и баннер (если появятся) обязаны уходить в stderr, не в stdout.
        stdout_tail = ""
        if proc.stdout and not proc.stdout.closed:
            stdout_tail = proc.stdout.read() or ""
        assert stdout_tail.strip() == "", (
            f"stdout после завершения содержит непротокольный вывод: {stdout_tail[:500]!r}"
        )


async def _subprocess_tool_names(env_extra: dict[str, str] | None = None) -> set[str]:
    """tools/list настоящего stdio-подпроцесса с заданным окружением."""
    command = _server_command()
    transport = StdioTransport(
        command=command[0],
        args=command[1:],
        cwd=PROJECT_ROOT,
        env=_clean_env(env_extra),
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
    return {tool.name for tool in tools}


async def test_subprocess_extended_toolset_visibility() -> None:
    """HH_TOOLSETS управляет extended: по умолчанию скрыт, при включении есть.

    HH_TOOLSETS полностью заменяет набор: чтобы auth остался alongside
    extended, он указывается явно.
    """
    default_names = await _subprocess_tool_names()
    assert "apply_to_vacancy" not in default_names  # extended выключен.
    assert "auth_status" in default_names  # auth в наборах по умолчанию.

    extended_names = await _subprocess_tool_names(
        {"HH_TOOLSETS": "auth,extended,dictionaries"}
    )
    assert "apply_to_vacancy" in extended_names
    assert "my_resumes" in extended_names
    assert "auth_status" in extended_names  # auth_status присутствует всегда.
