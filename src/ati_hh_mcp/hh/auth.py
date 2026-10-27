"""OAuth2 hh.ru: URL входа, обмен кода, refresh, отзыв и выбор токена.

Факты протокола (публичная OpenAPI hh.ru, операция ``authorize``):
- authorize: ``https://hh.ru/oauth/authorize?response_type=code&client_id=...
  &state=...&redirect_uri=...``;
- токен: ``POST /token`` с form-encoded телом (``grant_type`` равен
  ``authorization_code`` или ``refresh_token``);
- ответ: JSON ``{access_token, refresh_token, expires_in?, token_type}``
  (``expires_in`` может отсутствовать, поэтому актуальность проверяется
  по 401, а не по времени);
- отзыв: ``DELETE /token`` с текущим access-токеном (204 No Content).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

import httpx

from ..config import Config
from ..request_context import effective_profile, get_request_hh_token
from .client import CONNECT_TIMEOUT, READ_TIMEOUT, user_agent
from .errors import HHError, error_from_response
from .token_store import DEFAULT_PROFILE, StoredTokens, TokenStore

#: Страница входа hh.ru (домен hh.ru, не api.hh.ru).
HH_AUTHORIZE_URL = "https://hh.ru/oauth/authorize"

#: Путь операции токена на API-хосте.
TOKEN_PATH = "/token"

#: Тип do_request в TokenProvider.ensure_fresh.
RequestCall = Callable[[str], Awaitable[Any]]


def resolve_hh_token(
    config: Config,
    store: TokenStore,
    profile_key: str = DEFAULT_PROFILE,
) -> str | None:
    """Единый порядок выбора токена hh.ru (план, «Модель авторизации»).

    1. ``X-HH-Token`` текущего HTTP-запроса (stateless, без хранения);
    2. OAuth-профиль текущего пользователя (``effective_profile``:
       sha256 API-ключа в многопользовательском HTTP, ``default`` иначе);
    3. ``HH_TOKEN`` env – только когда ``MCP_API_KEYS`` не заданы
       (защита от смешения профилей пользователей).
    """
    header_token = get_request_hh_token()
    if header_token:
        return header_token
    profile = effective_profile(profile_key)
    tokens = store.get_tokens(profile)
    if tokens is not None:
        return tokens.access_token
    if not config.api_keys and profile == DEFAULT_PROFILE and config.token:
        return config.token
    return None


def _oauth_not_configured(varnames: str) -> HHError:
    """Ошибка «OAuth не настроен» с русской инструкцией по переменным."""
    return HHError(
        "oauth_not_configured",
        f"OAuth не настроен: не заданы переменные окружения ({varnames}).",
        hint="создайте приложение на https://dev.hh.ru/admin и задайте "
        "переменные окружения HH_CLIENT_ID, HH_CLIENT_SECRET и HH_REDIRECT_URI "
        "(redirect_uri должен совпадать с зарегистрированным в приложении)",
    )


class HHOAuth:
    """OAuth-клиент hh.ru поверх :class:`TokenStore`.

    Все HTTP-вызовы идут через ``httpx`` с инъекцией транспорта
    (``transport``) для тестов на моках.
    """

    def __init__(
        self,
        config: Config,
        store: TokenStore,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._transport = transport

    # ------------------------------------------------------------------
    # URL входа
    # ------------------------------------------------------------------
    def build_authorize_url(
        self,
        profile_key: str = DEFAULT_PROFILE,
        *,
        client_id: str | None = None,
        redirect_uri: str | None = None,
        state: str | None = None,
    ) -> str:
        """Собирает URL входа hh.ru с подписанным state текущего профиля.

        Профиль берётся из контекста запроса (HTTP-режим привязывает
        state к API-ключу пользователя), fallback – переданный аргумент.
        """
        profile_key = effective_profile(profile_key)
        effective_client_id = client_id or self._config.client_id
        effective_redirect_uri = redirect_uri or self._config.redirect_uri
        if not effective_client_id or not self._config.client_secret:
            missing = "HH_CLIENT_ID" if not effective_client_id else "HH_CLIENT_SECRET"
            raise _oauth_not_configured(missing)
        if not effective_redirect_uri:
            raise _oauth_not_configured("HH_REDIRECT_URI")
        params = {
            "response_type": "code",
            "client_id": effective_client_id,
            "redirect_uri": effective_redirect_uri,
            "state": state if state is not None else self._store.sign_state(profile_key),
        }
        return f"{HH_AUTHORIZE_URL}?{urlencode(params)}"

    # ------------------------------------------------------------------
    # HTTP к /token
    # ------------------------------------------------------------------
    def _http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._config.api_base,
            headers={
                "User-Agent": user_agent(self._config.ua_email),
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            transport=self._transport,
        )

    async def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        """POST /token с form-encoded телом; возвращает разобранный JSON."""
        async with self._http_client() as http:
            response = await http.post(TOKEN_PATH, data=form)
        if response.status_code >= 400:
            try:
                body: Any = response.json()
            except ValueError:
                body = None
            raise error_from_response(response.status_code, body) from None
        parsed: Any = response.json()
        if not isinstance(parsed, dict):
            raise HHError(
                "oauth_bad_response",
                "Ответ hh.ru на запрос токена не является JSON-объектом.",
            )
        return parsed

    @staticmethod
    def _require_client_credentials(config: Config) -> None:
        if not config.client_id or not config.client_secret:
            raise _oauth_not_configured("HH_CLIENT_ID, HH_CLIENT_SECRET")

    # ------------------------------------------------------------------
    # Обмен кода, refresh, отзыв
    # ------------------------------------------------------------------
    async def exchange_code(
        self,
        code: str,
        profile_key: str = DEFAULT_PROFILE,
    ) -> StoredTokens:
        """Обменивает authorization_code на пару токенов и сохраняет её.

        Профиль – из контекста запроса, если задан (HTTP-режим), иначе
        переданный аргумент.
        """
        profile_key = effective_profile(profile_key)
        self._require_client_credentials(self._config)
        form = {
            "grant_type": "authorization_code",
            "client_id": self._config.client_id or "",
            "client_secret": self._config.client_secret or "",
            "code": code,
        }
        if self._config.redirect_uri:
            form["redirect_uri"] = self._config.redirect_uri
        body = await self._token_request(form)
        return self._save_response(profile_key, body)

    async def refresh(self, profile_key: str = DEFAULT_PROFILE) -> StoredTokens:
        """Обновляет пару токенов профиля под блокировкой магазина."""
        profile_key = effective_profile(profile_key)
        async with self._store.lock:
            tokens = self._store.get_tokens(profile_key)
            if tokens is None or not tokens.refresh_token:
                raise HHError(
                    "no_refresh_token",
                    "Нет refresh-токена для обновления пары токенов.",
                    hint="выполните вход заново: auth_get_login_url -> "
                    "auth_exchange_code",
                )
            body = await self._token_request(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": tokens.refresh_token,
                }
            )
            return self._save_response(profile_key, body)

    async def revoke(self, profile_key: str = DEFAULT_PROFILE) -> dict[str, Any]:
        """Отзывает access-токен (DELETE /token) и удаляет профиль.

        Профиль удаляется в любом случае: если API отклонил отзыв
        (например, токен уже недействителен), локальные токены всё равно
        больше не должны использоваться. Возвращает словарь с флагом
        ``revoked`` и текстом ошибки, если она была.
        """
        profile_key = effective_profile(profile_key)
        tokens = self._store.get_tokens(profile_key)
        if tokens is None:
            return {
                "revoked": False,
                "profile": profile_key,
                "error": "профиль не найден: токенов нет",
            }
        error_text: str | None = None
        async with self._http_client() as http:
            response = await http.delete(
                TOKEN_PATH,
                headers={"Authorization": f"Bearer {tokens.access_token}"},
            )
        if response.status_code >= 400:
            try:
                body: Any = response.json()
            except ValueError:
                body = None
            error_text = error_from_response(response.status_code, body).description
        self._store.delete_profile(profile_key)
        return {"revoked": error_text is None, "profile": profile_key, "error": error_text}

    # ------------------------------------------------------------------
    # Вспомогательное
    # ------------------------------------------------------------------
    def _save_response(self, profile_key: str, body: dict[str, Any]) -> StoredTokens:
        """Извлекает пару токенов из ответа /token и сохраняет её."""
        access_token = body.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise HHError(
                "oauth_bad_response",
                "Ответ hh.ru не содержит access_token.",
            )
        refresh_token = body.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            refresh_token = None
        return self._store.save_tokens(profile_key, access_token, refresh_token)


class TokenProvider:
    """Слой выбора токена hh.ru и единичный refresh при ответе 401.

    Порядок выбора – :func:`resolve_hh_token`: ``X-HH-Token`` запроса ->
    OAuth-профиль текущего пользователя -> ``HH_TOKEN`` env (только без
    ``MCP_API_KEYS``). Профиль запроса (HTTP-режим) приоритетнее
    переданного аргумента.

    :meth:`ensure_fresh` выполняет запрос через ``do_request(token)`` и при
    ответе 401 (код ``unauthorized``) один раз обновляет пару токенов и
    повторяет запрос; если refresh не удался, наружу поднимается исходная
    ошибка 401.
    """

    def __init__(
        self,
        config: Config,
        store: TokenStore,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._oauth = HHOAuth(config, store, transport=transport)

    def resolve_token(self, profile_key: str = DEFAULT_PROFILE) -> str | None:
        """Токен hh.ru по порядку плана (см. :func:`resolve_hh_token`)."""
        return resolve_hh_token(self._config, self._store, profile_key)

    async def ensure_fresh(
        self,
        do_request: RequestCall,
        profile_key: str = DEFAULT_PROFILE,
    ) -> Any:
        """Выполняет запрос с текущим токеном; при 401 – refresh и повтор.

        Повтор выполняется один раз и только для GET-подобных запросов
        (безопасно повторять); мутации с 401 не повторяются.
        """
        token = self.resolve_token(profile_key)
        if token is None:
            raise HHError(
                "no_hh_token",
                "Не найден токен hh.ru для авторизованного запроса.",
                hint="задайте HH_TOKEN, передайте заголовок X-HH-Token "
                "или выполните OAuth-вход (auth_get_login_url)",
            )
        try:
            return await do_request(token)
        except HHError as err:
            if err.code != "unauthorized":
                raise
            original = err
        try:
            await self._oauth.refresh(profile_key)
        except HHError:
            # Refresh не удался – наружу уходит исходная ошибка 401.
            raise original from None
        refreshed = self.resolve_token(profile_key)
        if refreshed is None or refreshed == token:
            raise original from None
        return await do_request(refreshed)
