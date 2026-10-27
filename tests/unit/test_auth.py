"""Юнит-тесты OAuth-клиента и выбора токена (моки httpx)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from ati_hh_mcp.hh.auth import HH_AUTHORIZE_URL, HHOAuth, TokenProvider
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.hh.token_store import TokenStore

from ..conftest import make_config


@pytest.fixture
def store() -> Iterator[TokenStore]:
    """Хранилище на :memory: с закрытием после теста."""
    token_store = TokenStore()
    yield token_store
    token_store.close()


class OAuthMock:
    """Заглушка эндпоинтов авторизации: POST/DELETE /token."""

    def __init__(
        self,
        *,
        token_response: dict[str, Any] | None = None,
        delete_status: int = 204,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.token_response = (
            token_response
            if token_response is not None
            else {"access_token": "AT", "refresh_token": "RT", "token_type": "bearer"}
        )
        self.delete_status = delete_status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST" and request.url.path == "/token":
            return httpx.Response(200, json=self.token_response)
        if request.method == "DELETE" and request.url.path == "/token":
            return httpx.Response(self.delete_status)
        return httpx.Response(404, json={"errors": [{"type": "not_found"}]})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


class ScriptedMock:
    """Сценарий ensure_fresh: /me 401 -> /token -> /me 200."""

    def __init__(self, *, refresh_status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.me_calls = 0
        self.refresh_status = refresh_status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/me":
            self.me_calls += 1
            if self.me_calls == 1:
                return httpx.Response(
                    401,
                    json={"errors": [{"type": "oauth", "value": "bad_authorization"}]},
                )
            return httpx.Response(200, json={"id": "42", "last_name": "Иванов"})
        if request.url.path == "/token" and request.method == "POST":
            if self.refresh_status != 200:
                return httpx.Response(
                    self.refresh_status,
                    json={"error": "invalid_request", "error_description": "expired"},
                )
            return httpx.Response(
                200,
                json={"access_token": "AT2", "refresh_token": "RT2"},
            )
        return httpx.Response(404, json={"errors": [{"type": "not_found"}]})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def oauth_config(**overrides: Any):
    """Конфигурация с настроенным OAuth-приложением."""
    defaults: dict[str, Any] = {
        "client_id": "CID",
        "client_secret": "SECRET",
        "redirect_uri": "https://example.test/cb",
    }
    defaults.update(overrides)
    return make_config(**defaults)


# ----------------------------------------------------------------------
# URL входа
# ----------------------------------------------------------------------
def test_build_authorize_url_contains_signed_state(store: TokenStore) -> None:
    oauth = HHOAuth(oauth_config(), store)

    url = oauth.build_authorize_url("default")

    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == HH_AUTHORIZE_URL
    query = parse_qs(parsed.query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["CID"]
    assert query["redirect_uri"] == ["https://example.test/cb"]
    state = query["state"][0]
    assert state.startswith("default|")
    assert store.verify_state(state) == "default"


def test_build_authorize_url_without_client_id(store: TokenStore) -> None:
    oauth = HHOAuth(oauth_config(client_id=None), store)
    with pytest.raises(HHError) as excinfo:
        oauth.build_authorize_url("default")
    assert excinfo.value.code == "oauth_not_configured"
    assert "HH_CLIENT_ID" in excinfo.value.description


def test_build_authorize_url_without_redirect_uri(store: TokenStore) -> None:
    oauth = HHOAuth(oauth_config(redirect_uri=None), store)
    with pytest.raises(HHError) as excinfo:
        oauth.build_authorize_url("default")
    assert excinfo.value.code == "oauth_not_configured"
    assert "HH_REDIRECT_URI" in excinfo.value.description


# ----------------------------------------------------------------------
# exchange / refresh / revoke
# ----------------------------------------------------------------------
async def test_exchange_code_posts_form_and_saves_tokens(store: TokenStore) -> None:
    mock = OAuthMock()
    oauth = HHOAuth(oauth_config(), store, transport=mock.transport)

    saved = await oauth.exchange_code("CODE-1", "default")

    assert saved.access_token == "AT"
    assert saved.refresh_token == "RT"
    request = mock.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/token"
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    body = parse_qs(request.content.decode("utf-8"))
    assert body["grant_type"] == ["authorization_code"]
    assert body["client_id"] == ["CID"]
    assert body["client_secret"] == ["SECRET"]
    assert body["code"] == ["CODE-1"]
    assert body["redirect_uri"] == ["https://example.test/cb"]
    assert store.get_tokens("default").access_token == "AT"


async def test_exchange_code_without_credentials(store: TokenStore) -> None:
    oauth = HHOAuth(oauth_config(client_secret=None), store)
    with pytest.raises(HHError) as excinfo:
        await oauth.exchange_code("CODE")
    assert excinfo.value.code == "oauth_not_configured"


async def test_refresh_posts_grant_and_updates_store(store: TokenStore) -> None:
    mock = OAuthMock(token_response={"access_token": "AT2", "refresh_token": "RT2"})
    store.save_tokens("default", "AT1", "RT1")
    oauth = HHOAuth(oauth_config(), store, transport=mock.transport)

    saved = await oauth.refresh("default")

    assert saved.access_token == "AT2"
    request = mock.requests[0]
    body = parse_qs(request.content.decode("utf-8"))
    assert body["grant_type"] == ["refresh_token"]
    assert body["refresh_token"] == ["RT1"]
    assert store.get_tokens("default").refresh_token == "RT2"


async def test_refresh_without_stored_tokens(store: TokenStore) -> None:
    oauth = HHOAuth(oauth_config(), store)
    with pytest.raises(HHError) as excinfo:
        await oauth.refresh("default")
    assert excinfo.value.code == "no_refresh_token"


async def test_revoke_deletes_token_and_profile(store: TokenStore) -> None:
    mock = OAuthMock(delete_status=204)
    store.save_tokens("default", "AT", "RT")
    oauth = HHOAuth(oauth_config(), store, transport=mock.transport)

    result = await oauth.revoke("default")

    request = mock.requests[0]
    assert request.method == "DELETE"
    assert request.url.path == "/token"
    assert request.headers["authorization"] == "Bearer AT"
    assert result == {"revoked": True, "profile": "default", "error": None}
    assert store.get_tokens("default") is None


async def test_revoke_api_error_still_deletes_profile(store: TokenStore) -> None:
    mock = OAuthMock(delete_status=403)
    store.save_tokens("default", "AT", "RT")
    oauth = HHOAuth(oauth_config(), store, transport=mock.transport)

    result = await oauth.revoke("default")

    assert result["revoked"] is False
    assert result["error"]
    assert store.get_tokens("default") is None


async def test_revoke_missing_profile(store: TokenStore) -> None:
    mock = OAuthMock()
    oauth = HHOAuth(oauth_config(), store, transport=mock.transport)

    result = await oauth.revoke("default")

    assert result["revoked"] is False
    assert mock.requests == []


# ----------------------------------------------------------------------
# TokenProvider.resolve_token
# ----------------------------------------------------------------------
def test_resolve_token_env_only_for_default_profile(store: TokenStore) -> None:
    provider = TokenProvider(oauth_config(token="ENV-TOKEN"), store)

    assert provider.resolve_token("default") == "ENV-TOKEN"
    # Другой профиль env-токен не получает (защита от смешения профилей).
    assert provider.resolve_token("profile-b") is None


def test_resolve_token_prefers_store_for_non_default(store: TokenStore) -> None:
    store.save_tokens("profile-b", "STORE-B", "RT-B")
    provider = TokenProvider(oauth_config(token="ENV-TOKEN"), store)

    assert provider.resolve_token("profile-b") == "STORE-B"
    assert provider.resolve_token("default") == "ENV-TOKEN"


def test_resolve_token_from_store_when_env_missing(store: TokenStore) -> None:
    store.save_tokens("default", "STORE-AT", None)
    provider = TokenProvider(oauth_config(), store)

    assert provider.resolve_token("default") == "STORE-AT"


# ----------------------------------------------------------------------
# TokenProvider.ensure_fresh
# ----------------------------------------------------------------------
async def test_ensure_fresh_success_without_refresh(store: TokenStore) -> None:
    mock = ScriptedMock(refresh_status=999)  # /token не должен вызываться
    provider = TokenProvider(oauth_config(token="ENV"), store, transport=mock.transport)

    async def do_request(token: str) -> Any:
        return {"token": token, "ok": True}

    result = await provider.ensure_fresh(do_request)
    assert result == {"token": "ENV", "ok": True}
    assert mock.requests == []


async def test_ensure_fresh_retries_once_after_401(store: TokenStore) -> None:
    mock = ScriptedMock()
    store.save_tokens("default", "AT1", "RT1")
    provider = TokenProvider(oauth_config(), store, transport=mock.transport)
    seen: list[str] = []

    def do_request(token: str):
        async def _call() -> Any:
            seen.append(token)
            client = HHClient(
                replace(oauth_config(), token=token), transport=mock.transport
            )
            try:
                return await client.get("/me")
            finally:
                await client.aclose()

        return _call()

    result = await provider.ensure_fresh(do_request)

    assert result == {"id": "42", "last_name": "Иванов"}
    assert seen == ["AT1", "AT2"]
    assert mock.me_calls == 2
    assert store.get_tokens("default").access_token == "AT2"


async def test_ensure_fresh_refresh_failure_reraises_original_401(
    store: TokenStore,
) -> None:
    mock = ScriptedMock(refresh_status=400)
    store.save_tokens("default", "AT1", "RT1-bad")
    provider = TokenProvider(oauth_config(), store, transport=mock.transport)

    async def do_request(token: str) -> Any:
        client = HHClient(replace(oauth_config(), token=token), transport=mock.transport)
        try:
            return await client.get("/me")
        finally:
            await client.aclose()

    with pytest.raises(HHError) as excinfo:
        await provider.ensure_fresh(do_request)
    # Наружу – исходная ошибка 401, а не ошибка refresh.
    assert excinfo.value.code == "unauthorized"
    assert mock.me_calls == 1


async def test_ensure_fresh_env_token_401_reraises_original(store: TokenStore) -> None:
    """Env-токен нельзя обновить: без store-профиля исходная 401."""
    mock = ScriptedMock()
    provider = TokenProvider(
        oauth_config(token="ENV"), store, transport=mock.transport
    )

    async def do_request(token: str) -> Any:
        client = HHClient(replace(oauth_config(), token=token), transport=mock.transport)
        try:
            return await client.get("/me")
        finally:
            await client.aclose()

    with pytest.raises(HHError) as excinfo:
        await provider.ensure_fresh(do_request)
    assert excinfo.value.code == "unauthorized"


async def test_ensure_fresh_without_token_raises(store: TokenStore) -> None:
    provider = TokenProvider(oauth_config(), store)

    async def do_request(token: str) -> Any:
        raise AssertionError("не должен вызываться без токена")

    with pytest.raises(HHError) as excinfo:
        await provider.ensure_fresh(do_request)
    assert excinfo.value.code == "no_hh_token"
    assert "X-HH-Token" in (excinfo.value.hint or "")
