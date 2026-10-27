"""Сборка MCP-сервера из наборов инструментов.

Наборы подключаются по ``config.toolsets`` через ``TOOLSET_MODULES``.
Набор ``auth`` получает единый на процесс ``TokenStore`` (SQLite по пути
``auth_tools.default_store_path()``); остальные наборы подключаются
стандартным контрактом ``register(mcp, client_factory)``.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Protocol, cast

from fastmcp import FastMCP

from . import __version__, toolkit
from .config import Config
from .hh.client import HHClient
from .hh.token_store import TokenStore
from .toolsets import auth_tools

INSTRUCTIONS = (
    "MCP server for the hh.ru API. Tools are grouped into switchable "
    "toolsets; call the dict_* tools first to resolve ids for search "
    "parameters. Errors come as structured messages with hh.ru error codes "
    "and Russian descriptions."
)


class ToolsetModule(Protocol):
    """Контракт модуля набора инструментов (волна 2)."""

    TOOLSET_NAME: str

    def register(
        self, mcp: FastMCP, client_factory: toolkit.ClientFactory | None = None
    ) -> None: ...


# Реализованные наборы: имя -> модуль с TOOLSET_NAME и register(mcp, factory).
_TOOLSET_MODULE_NAMES: dict[str, str] = {
    "auth": "ati_hh_mcp.toolsets.auth_tools",
    "dictionaries": "ati_hh_mcp.toolsets.dictionaries",
    "suggests": "ati_hh_mcp.toolsets.suggests",
    "vacancies": "ati_hh_mcp.toolsets.vacancies",
    "extended": "ati_hh_mcp.toolsets.extended",
}

TOOLSET_MODULES: dict[str, ModuleType] = {
    name: import_module(module_name) for name, module_name in _TOOLSET_MODULE_NAMES.items()
}

# Единое хранилище OAuth-токенов на процесс (ключ – путь базы).
_process_store: TokenStore | None = None
_process_store_path: str | None = None


def shared_token_store() -> TokenStore:
    """Хранилище токенов на процесс по пути ``auth_tools.default_store_path()``.

    Пересоздаётся, если путь изменился (тесты подменяют HH_TOKEN_STORE).
    """
    global _process_store, _process_store_path
    path = auth_tools.default_store_path()
    if _process_store is None or _process_store_path != str(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        _process_store = TokenStore(path)
        _process_store_path = str(path)
    return _process_store


def build_server(config: Config | None = None) -> FastMCP:
    """Собирает FastMCP-приложение с наборами из config.toolsets."""
    cfg = config if config is not None else Config.from_env()

    # Фабрика клиентов привязывается к конфигурации сборки.
    def client_factory() -> HHClient:
        return HHClient(cfg)

    toolkit.set_client_factory(client_factory)

    server = FastMCP(name="ati-hh-mcp", version=__version__, instructions=INSTRUCTIONS)

    for name in cfg.toolsets:
        module = TOOLSET_MODULES.get(name)
        if module is None:
            continue  # набор ещё не реализован (последующие волны)
        if name == "auth":
            # auth нужен общий config/store: токен выбирается на каждый вызов.
            auth_tools.register(server, client_factory, config=cfg, store=shared_token_store())
        else:
            cast(ToolsetModule, module).register(server, client_factory)

    return server
