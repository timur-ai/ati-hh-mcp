"""Набор «auth»: OAuth-вход hh.ru и информация о текущем пользователе.

Инструменты:
- ``get_me`` – операция ``GET /me`` (требует токен hh.ru);
- ``auth_get_login_url`` / ``auth_exchange_code`` / ``auth_status`` –
  служебные инструменты OAuth-входа без операции OpenAPI (в реестре
  помечены плейсхолдером ``INTERNAL auth:*``);
- ``auth_logout`` – операция ``DELETE /token`` (мутация, требует confirm).

Параметр ``client_factory`` контракта toolset-модулей принимается для
совместимости, но OAuth-инструментам он не подходит: токен выбирается
на каждый вызов (env/профиль), поэтому клиенты строятся внутри
инструментов из ``config``/``transport``.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP

from ..config import Config
from ..hh.auth import HHOAuth, TokenProvider
from ..hh.client import HHClient
from ..hh.errors import HHError
from ..hh.token_store import DEFAULT_PROFILE, TokenStore
from ..registry import REGISTRY, ToolEntry

TOOLSET_NAME = "auth"

#: Переменная окружения с путём к SQLite-базе OAuth-токенов.
TOKEN_STORE_ENV = "HH_TOKEN_STORE"

#: Путь по умолчанию (персональный запуск; в Docker монтируется volume).
_TOKEN_STORE_DEFAULT = Path("~/.local/state/ati-hh-mcp/tokens.sqlite3")

#: Русская инструкция к URL входа (stdio-путь OAuth).
_LOGIN_INSTRUCTIONS = (
    "Откройте ссылку, авторизуйтесь на hh.ru, скопируйте параметр code "
    "из адресной строки после редиректа и вызовите auth_exchange_code"
)

#: Подсказка о сроке жизни токена (expires_in может отсутствовать).
_EXPIRES_HINT = (
    "Токен действует ограниченное время; hh.ru не всегда возвращает "
    "expires_in, поэтому при ответе 401 сервер обновит пару токены "
    "автоматически по refresh-токену"
)


def default_store_path() -> Path:
    """Путь к базе токенов: env HH_TOKEN_STORE или домашний каталог."""
    raw = os.environ.get(TOKEN_STORE_ENV)
    if raw:
        return Path(raw).expanduser()
    return _TOKEN_STORE_DEFAULT.expanduser()


def _open_default_store() -> TokenStore:
    """Открывает (и создаёт каталоги) базу токенов по умолчанию."""
    path = default_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return TokenStore(path)


def _confirm_required() -> HHError:
    """Ошибка не подтверждённой мутации (единая семантика с toolkit)."""
    return HHError("confirm_required", "Подтвердите операцию: передайте confirm=True.")


def register(
    mcp: FastMCP,
    client_factory: Any = None,  # noqa: ARG001 – контракт toolset-модулей
    *,
    config: Config | None = None,
    store: TokenStore | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Подключает пять инструментов набора «auth» к серверу.

    Параметры:
        mcp: сервер FastMCP.
        client_factory: фабрика HHClient (контракт toolset-модулей; для
            OAuth-инструментов не используется – см. докстринг модуля).
        config: конфигурация; по умолчанию собирается из окружения.
        store: хранилище токенов; по умолчанию открывается база по
            ``HH_TOKEN_STORE`` либо ``~/.local/state/ati-hh-mcp/``.
        transport: инъекция httpx-транспорта (тесты на моках).
    """
    effective_config = config if config is not None else Config.from_env()
    effective_store = store if store is not None else _open_default_store()

    # -- записи реестра (идемпотентны при повторной регистрации) -------
    REGISTRY.register(
        ToolEntry(
            name="get_me",
            operation_id="GET /me",
            toolset=TOOLSET_NAME,
            requires_auth=True,
            is_mutation=False,
        )
    )
    for name, operation_id in (
        ("auth_get_login_url", "INTERNAL auth:login_url"),
        ("auth_exchange_code", "INTERNAL auth:exchange_code"),
        ("auth_status", "INTERNAL auth:status"),
    ):
        REGISTRY.register(
            ToolEntry(
                name=name,
                operation_id=operation_id,
                toolset=TOOLSET_NAME,
                requires_auth=False,
                is_mutation=False,
            )
        )
    REGISTRY.register(
        ToolEntry(
            name="auth_logout",
            operation_id="DELETE /token",
            toolset=TOOLSET_NAME,
            requires_auth=True,
            is_mutation=True,
        )
    )

    # -- get_me ---------------------------------------------------------
    async def get_me() -> Any:
        """Get information about the current hh.ru user (GET /me).

        Requires an hh.ru token (HH_TOKEN env, X-HH-Token header or OAuth
        profile). If the token has expired, the server refreshes the OAuth
        pair and retries the request once.
        """
        provider = TokenProvider(effective_config, effective_store, transport=transport)

        async def _call(token: str) -> Any:
            client = HHClient(replace(effective_config, token=token), transport=transport)
            try:
                return await client.get("/me")
            finally:
                await client.aclose()

        return await provider.ensure_fresh(_call)

    # -- auth_get_login_url ----------------------------------------------
    async def auth_get_login_url() -> dict[str, str]:
        """Get the hh.ru OAuth login URL (manual code copy flow).

        Returns the authorize URL and Russian instructions: open the URL,
        log in on hh.ru, copy the `code` query parameter from the redirect
        address and pass it to auth_exchange_code.
        """
        oauth = HHOAuth(effective_config, effective_store, transport=transport)
        url = oauth.build_authorize_url(DEFAULT_PROFILE)
        return {"url": url, "instructions": _LOGIN_INSTRUCTIONS}

    # -- auth_exchange_code ----------------------------------------------
    async def auth_exchange_code(code: str) -> dict[str, Any]:
        """Exchange an hh.ru OAuth authorization code for token pair.

        Use after auth_get_login_url: pass the `code` parameter copied
        from the redirect address. Tokens are stored in the local profile.
        """
        oauth = HHOAuth(effective_config, effective_store, transport=transport)
        await oauth.exchange_code(code, DEFAULT_PROFILE)
        return {"ok": True, "expires_hint": _EXPIRES_HINT}

    # -- auth_status ------------------------------------------------------
    async def auth_status() -> dict[str, Any]:
        """Show OAuth configuration and stored token status.

        Reports whether OAuth client credentials are configured, whether
        a token pair is stored for the current profile, and when it was
        obtained.
        """
        tokens = effective_store.get_tokens(DEFAULT_PROFILE)
        return {
            "configured": bool(
                effective_config.client_id and effective_config.client_secret
            ),
            "has_tokens": tokens is not None,
            "profile": DEFAULT_PROFILE,
            "obtained_at": tokens.obtained_at if tokens is not None else None,
        }

    # -- auth_logout ------------------------------------------------------
    async def auth_logout(confirm: bool = False) -> dict[str, Any]:
        """Revoke the hh.ru OAuth token and delete the local profile.

        Calls DELETE /token on hh.ru (invalidates the token pair) and
        removes stored tokens. Mutation: requires confirm=True.
        """
        if not confirm:
            raise _confirm_required()
        oauth = HHOAuth(effective_config, effective_store, transport=transport)
        return await oauth.revoke(DEFAULT_PROFILE)

    for tool in (get_me, auth_get_login_url, auth_exchange_code, auth_status, auth_logout):
        mcp.tool(tool)
