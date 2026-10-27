"""Сборка MCP-сервера из наборов инструментов."""

from __future__ import annotations

from fastmcp import FastMCP

from . import __version__, toolkit
from .config import Config
from .hh.client import HHClient

INSTRUCTIONS = (
    "MCP server for the hh.ru API. Tools are grouped into switchable "
    "toolsets; call the dict_* tools first to resolve ids for search "
    "parameters. Errors come as structured messages with hh.ru error codes "
    "and Russian descriptions."
)


def build_server(config: Config | None = None) -> FastMCP:
    """Собирает FastMCP-приложение с наборами из config.toolsets.

    В M1 подключается только набор «dictionaries» (вертикальный срез);
    остальные наборы добавляются на этапах M3+.
    """
    cfg = config if config is not None else Config.from_env()

    # Фабрика клиентов привязывается к конфигурации сборки.
    toolkit.set_client_factory(lambda: HHClient(cfg))

    server = FastMCP(name="ati-hh-mcp", version=__version__, instructions=INSTRUCTIONS)

    from .toolsets import dictionaries

    if "dictionaries" in cfg.toolsets:
        dictionaries.register(server)

    return server
