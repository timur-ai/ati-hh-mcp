"""Тесты CLI (__main__): версия, разбор аргументов, ветки транспорта."""

from __future__ import annotations

import pytest

from ati_hh_mcp import __main__ as cli
from ati_hh_mcp import __version__

from ..conftest import make_config


class _FakeConfig:
    """Config.from_env -> тестовая конфигурация (без env-зависимостей)."""

    @staticmethod
    def from_env() -> object:
        return make_config()


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert f"ati-hh-mcp {__version__}" in capsys.readouterr().out


def test_parser_defaults() -> None:
    args = cli.build_parser().parse_args(["serve"])
    assert args.transport == "stdio"
    assert args.host == "0.0.0.0"
    assert args.port == 8080
    assert args.toolsets is None


def test_parser_toolsets_override() -> None:
    args = cli.build_parser().parse_args(["serve", "--toolsets", "dictionaries,extended"])
    assert args.toolsets == "dictionaries,extended"


def test_parser_http_host_port(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(
        ["serve", "--transport", "http", "--host", "127.0.0.1", "--port", "9999"]
    )
    assert args.transport == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 9999


def test_serve_stdio_runs_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """stdio-ветка запускает run_async (подменён, чтобы не блокировать)."""
    started: list[dict[str, object]] = []

    class _FakeServer:
        async def run_async(self, **kwargs: object) -> None:
            started.append(kwargs)

    monkeypatch.setattr(cli, "build_server", lambda _cfg: _FakeServer())
    monkeypatch.setattr(cli, "Config", _FakeConfig)
    code = cli.main(["serve"])
    assert code == 0
    assert started == [{"transport": "stdio", "show_banner": False}]


def test_serve_http_runs_http_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """http-ветка запускает run_http_async с middleware гейта."""
    started: list[dict[str, object]] = []

    class _FakeServer:
        async def run_http_async(self, **kwargs: object) -> None:
            started.append(kwargs)

    monkeypatch.setattr(cli, "build_http_server", lambda _cfg: _FakeServer())
    monkeypatch.setattr(cli, "Config", _FakeConfig)
    code = cli.main(
        ["serve", "--transport", "http", "--host", "127.0.0.1", "--port", "8123"]
    )
    assert code == 0
    assert len(started) == 1
    kwargs = started[0]
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8123
    assert kwargs["show_banner"] is False
    assert len(kwargs["middleware"]) == 1  # гейт RequestAuthMiddleware.


# --- guard открытого HTTP (team-fix, M-medium) ------------------------------


def test_http_open_server_on_non_loopback_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """0.0.0.0 без MCP_API_KEYS – отказ (exit 2), сервер не стартует."""
    started: list[str] = []

    class _NeverServer:
        async def run_http_async(self, **kwargs: object) -> None:  # pragma: no cover
            started.append("must not run")

    monkeypatch.setattr(cli, "build_http_server", lambda _cfg: _NeverServer())
    monkeypatch.setattr(cli, "_FakeConfig", _FakeConfig, raising=False)
    monkeypatch.setattr(cli, "Config", _FakeConfig)
    code = cli.main(["serve", "--transport", "http", "--host", "0.0.0.0"])
    assert code == 2
    assert started == []
    stderr = capsys.readouterr().err
    assert "MCP_API_KEYS" in stderr
    assert "127.0.0.1" in stderr


def test_http_open_server_on_loopback_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """127.0.0.1 без ключей – личный запуск разрешён."""
    started: list[dict[str, object]] = []

    class _FakeServer:
        async def run_http_async(self, **kwargs: object) -> None:
            started.append(kwargs)

    monkeypatch.setattr(cli, "build_http_server", lambda _cfg: _FakeServer())
    monkeypatch.setattr(cli, "Config", _FakeConfig)
    code = cli.main(["serve", "--transport", "http", "--host", "127.0.0.1"])
    assert code == 0
    assert len(started) == 1


def test_http_server_with_api_keys_on_any_host_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0.0.0.0 с MCP_API_KEYS – штатный запуск."""

    class _KeyConfig:
        @staticmethod
        def from_env() -> object:
            return make_config(api_keys=("key-a",))

    started: list[dict[str, object]] = []

    class _FakeServer:
        async def run_http_async(self, **kwargs: object) -> None:
            started.append(kwargs)

    monkeypatch.setattr(cli, "build_http_server", lambda _cfg: _FakeServer())
    monkeypatch.setattr(cli, "Config", _KeyConfig)
    code = cli.main(["serve", "--transport", "http", "--host", "0.0.0.0"])
    assert code == 0
    assert len(started) == 1


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("LOCALHOST", True),
        ("::1", True),
        ("[::1]", True),
        ("0.0.0.0", False),
        ("192.168.1.5", False),
        ("example.com", False),
    ],
)
def test_is_loopback(host: str, expected: bool) -> None:
    assert cli._is_loopback(host) is expected
