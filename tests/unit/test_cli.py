"""Тесты CLI (__main__): версия, заглушка HTTP, разбор аргументов."""

from __future__ import annotations

import pytest

from ati_hh_mcp import __main__ as cli
from ati_hh_mcp import __version__


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert f"ati-hh-mcp {__version__}" in capsys.readouterr().out


def test_http_transport_stub(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("HH_TOKEN", "HH_TOOLSETS", "HH_API_BASE", "HH_UA_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    code = cli.main(["serve", "--transport", "http"])
    assert code == 2
    assert "M7" in capsys.readouterr().err


def test_parser_defaults() -> None:
    args = cli.build_parser().parse_args(["serve"])
    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.toolsets is None


def test_parser_toolsets_override() -> None:
    args = cli.build_parser().parse_args(["serve", "--toolsets", "dictionaries,extended"])
    assert args.toolsets == "dictionaries,extended"
