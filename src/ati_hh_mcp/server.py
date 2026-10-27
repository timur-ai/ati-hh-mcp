"""Сборка MCP-сервера из наборов инструментов.

Наборы подключаются по ``config.toolsets`` через ``TOOLSET_MODULES``;
набор ``auth`` подключается всегда, даже если не перечислен в
``HH_TOOLSETS`` (OAuth-вход – единственный путь обновления токенов и не
должен теряться при замене списка). Набор ``auth`` получает единый на
процесс ``TokenStore`` (SQLite по пути ``auth_tools.default_store_path()``);
остальные наборы подключаются стандартным контрактом
``register(mcp, client_factory)``.

HTTP-транспорт (этап M7): ``build_http_server`` добавляет маршруты
``/health`` (проверка живости, без авторизации) и ``/oauth/callback``
(callback OAuth-входа), ``RequestAuthMiddleware`` закрывает сервер
API-ключами ``MCP_API_KEYS`` и фиксирует контекст запроса (заголовок
``X-HH-Token`` + OAuth-профиль) для фабрики клиентов.
"""

from __future__ import annotations

import hmac
import importlib
import json
import logging
import sys
from dataclasses import replace
from types import ModuleType
from typing import Protocol, cast

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from . import __version__, request_context, toolkit
from .config import Config
from .hh.auth import HHOAuth, resolve_hh_token
from .hh.client import HHClient
from .hh.errors import HHError
from .hh.token_store import DEFAULT_PROFILE, TokenStore, profile_key_from_api_key
from .toolsets import auth_tools

# Журнал безопасности: отказы доступа и обмены OAuth-кода. Обработчик
# пишет в stderr (в stdio-режиме stdout обязан содержать только протокол
# MCP); в записях нет токенов, кодов авторизации и тел запросов.
security_log = logging.getLogger("ati-hh-mcp.security")
if not security_log.handlers:
    _security_handler = logging.StreamHandler(sys.stderr)
    _security_handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    security_log.addHandler(_security_handler)
    security_log.setLevel(logging.INFO)

INSTRUCTIONS = (
    "MCP server for the hh.ru API. Tools are grouped into switchable "
    "toolsets; call the dict_* tools first to resolve ids for search "
    "parameters. Errors come as structured messages with hh.ru error codes "
    "and Russian descriptions."
)

#: Маршруты вне гейта MCP_API_KEYS (проверка живости и OAuth-callback).
PUBLIC_PATHS = frozenset({"/health", "/oauth/callback"})


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
    "negotiations": "ati_hh_mcp.toolsets.negotiations",
    "chats": "ati_hh_mcp.toolsets.chats",
    "resumes": "ati_hh_mcp.toolsets.resumes",
    "employer_vacancies": "ati_hh_mcp.toolsets.employer_vacancies",
    "employer_negotiations": "ati_hh_mcp.toolsets.employer_negotiations",
    "employer_resumes": "ati_hh_mcp.toolsets.employer_resumes",
    "employer_managers": "ati_hh_mcp.toolsets.employer_managers",
    "employer_misc": "ati_hh_mcp.toolsets.employer_misc",
    "extended": "ati_hh_mcp.toolsets.extended",
}

TOOLSET_MODULES: dict[str, ModuleType] = {
    name: importlib.import_module(module_name)
    for name, module_name in _TOOLSET_MODULE_NAMES.items()
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


def _effective_toolsets(config: Config) -> tuple[str, ...]:
    """Список подключаемых наборов: config.toolsets + всегда auth."""
    if "auth" in config.toolsets:
        return config.toolsets
    return ("auth", *config.toolsets)


def build_server(config: Config | None = None) -> FastMCP:
    """Собирает FastMCP-приложение с наборами из config.toolsets.

    Набор ``auth`` принудительно добавляется, даже если не перечислен в
    ``HH_TOOLSETS``: без него теряется единственный путь OAuth-входа
    (``auth_get_login_url``/``auth_exchange_code``/``auth_logout``).
    """
    cfg = config if config is not None else Config.from_env()
    store = shared_token_store()

    # Фабрика клиентов привязывается к конфигурации сборки; токен hh.ru
    # выбирается на каждый вызов: X-HH-Token запроса -> OAuth-профиль ->
    # HH_TOKEN env (только без MCP_API_KEYS).
    def client_factory() -> HHClient:
        token = resolve_hh_token(cfg, store)
        return HHClient(replace(cfg, token=token))

    toolkit.set_client_factory(client_factory)

    server = FastMCP(name="ati-hh-mcp", version=__version__, instructions=INSTRUCTIONS)

    for name in _effective_toolsets(cfg):
        module = TOOLSET_MODULES.get(name)
        if module is None:
            continue  # набор ещё не реализован (последующие волны)
        if name == "auth":
            # auth нужен общий config/store: токен выбирается на каждый вызов.
            auth_tools.register(server, client_factory, config=cfg, store=store)
        else:
            cast(ToolsetModule, module).register(server, client_factory)

    return server


# --- HTTP-транспорт: гейт API-ключей и контекст запроса ---------------------


class RequestAuthMiddleware:
    """ASGI-middleware: гейт ``MCP_API_KEYS`` + контекст запроса.

    При заданных API-ключах каждый запрос (кроме ``PUBLIC_PATHS``) обязан
    нести ``Authorization: Bearer <key>``; ключ сверяется со списком
    через ``hmac.compare_digest`` по байтам utf-8 (не-ASCII значения не
    вызывают исключений, а дают отказ). Неверный или отсутствующий ключ –
    ``401`` с JSON-ошибкой на русском; попытка WebSocket-соединения
    закрывается кодом 1008 (гейт не поддерживает WS-рукопожатие).

    Для прошедших проверку (и в открытом режиме без ключей) middleware
    фиксирует контекст запроса: заголовок ``X-HH-Token`` и профиль
    (sha256 API-ключа либо ``default``).
    """

    def __init__(self, app: ASGIApp, api_keys: tuple[str, ...] = ()) -> None:
        self.app = app
        self._api_keys = tuple(api_keys)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            if self._api_keys:
                security_log.warning("unauthorized ws handshake path=%s", scope.get("path"))
                await send({"type": "websocket.accept"})
                await send({"type": "websocket.close", "code": 1008, "reason": "unauthorized"})
                return
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http" or scope.get("path") in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        api_key = self._validated_api_key(headers.get("authorization", ""))
        if self._api_keys and api_key is None:
            security_log.warning("unauthorized path=%s", scope.get("path"))
            await _send_unauthorized(send)
            return

        profile = profile_key_from_api_key(api_key) if api_key else DEFAULT_PROFILE
        request_context.set_request_auth(
            hh_token=headers.get("x-hh-token") or None,
            profile=profile,
        )
        await self.app(scope, receive, send)

    def _validated_api_key(self, authorization: str) -> str | None:
        """Возвращает валидированный API-ключ или None (нет/не совпал)."""
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            return None
        presented = value.strip().encode("utf-8")
        for known in self._api_keys:
            # Сравнение по байтам: не-ASCII Bearer не роняет сервер.
            if hmac.compare_digest(presented, known.encode("utf-8")):
                return known
        return None


async def _send_unauthorized(send: Send) -> None:
    """Ответ 401 с JSON-ошибкой на русском (формат ошибок проекта)."""
    body = json.dumps(
        {
            "error": {
                "code": "unauthorized",
                "description": (
                    "Доступ к MCP-серверу запрещён: неверный или отсутствующий "
                    "API-ключ. Передайте заголовок Authorization: Bearer <ключ> "
                    "из списка MCP_API_KEYS."
                ),
            }
        },
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": body})


# --- HTTP-маршруты: /health и /oauth/callback --------------------------------


def build_http_server(config: Config | None = None) -> FastMCP:
    """Собирает сервер с HTTP-маршрутами /health и /oauth/callback."""
    cfg = config if config is not None else Config.from_env()
    store = shared_token_store()
    server = build_server(cfg)

    @server.custom_route("/health", methods=["GET"], name="health")
    async def health(_request: Request) -> JSONResponse:
        """Проверка живости сервера (без авторизации)."""
        return JSONResponse({"status": "ok", "version": __version__})

    @server.custom_route("/oauth/callback", methods=["GET"], name="oauth-callback")
    async def oauth_callback(request: Request) -> PlainTextResponse:
        """OAuth-callback hh.ru: state -> профиль, code -> пара токенов.

        Человекочитаемый ответ (страницу открывает браузер человека),
        коды: 200 – успех, 400 – некорректные параметры/state,
        502 – hh.ru отклонил обмен кода или сеть недоступна.
        """
        code = request.query_params.get("code", "")
        state = request.query_params.get("state", "")
        if not code or not state:
            return PlainTextResponse(
                "Некорректный запрос OAuth-callback: обязательны параметры "
                "code и state.",
                status_code=400,
            )
        profile = store.verify_state(state)
        if profile is None:
            security_log.warning("oauth_exchange fail reason=bad_state")
            return PlainTextResponse(
                "Не удалось проверить параметр state: подпись недействительна "
                "или срок действия истёк. Начните вход заново (auth_get_login_url).",
                status_code=400,
            )
        try:
            await HHOAuth(cfg, store).exchange_code(code, profile)
        except HHError as err:
            security_log.warning("oauth_exchange fail profile=%s code=%s", profile, err.code)
            return PlainTextResponse(
                f"Не удалось получить токены hh.ru: {err.description}",
                status_code=502,
            )
        except httpx.TransportError:
            security_log.warning(
                "oauth_exchange fail profile=%s reason=network", profile
            )
            return PlainTextResponse(
                "Не удалось связаться с hh.ru для обмена кода: сетевая ошибка. "
                "Проверьте соединение сервера с api.hh.ru и повторите вход.",
                status_code=502,
            )
        security_log.info("oauth_exchange ok profile=%s", profile)
        return PlainTextResponse(
            "Готово: токены hh.ru получены и сохранены. Можно вернуться к "
            "MCP-клиенту и вызывать инструменты (например, get_me)."
        )

    return server
