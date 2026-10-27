"""Порядок выбора токена hh.ru и изоляция OAuth-профилей (этап M7).

Инварианты плана («Модель авторизации»):
- X-HH-Token запроса приоритетнее OAuth-профиля и env;
- профиль запроса (sha256 API-ключа) приоритетнее env HH_TOKEN;
- env HH_TOKEN отключён при заданных MCP_API_KEYS (нет смешения профилей);
- профили пользователей A и B изолированы: токен A недоступен в запросе B;
- в stdio (контекст не задан) действует fallback ``default`` и env.
"""

from __future__ import annotations

import httpx
import pytest

from ati_hh_mcp import request_context
from ati_hh_mcp.hh.auth import HHOAuth, TokenProvider, resolve_hh_token
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.hh.token_store import TokenStore, profile_key_from_api_key

from ..conftest import make_config


def _oauth_config() -> object:
    return make_config(
        client_id="CID", client_secret="SECRET", redirect_uri="https://example.test/cb"
    )


@pytest.fixture(autouse=True)
def clean_request_context() -> None:
    """Каждый тест начинается без контекста запроса."""
    request_context.set_request_auth(hh_token=None, profile=None)


def test_stdio_env_token_used_without_context() -> None:
    """Без контекста (stdio) и без профиля – работает env HH_TOKEN."""
    store = TokenStore()
    config = make_config(token="env-token")
    assert resolve_hh_token(config, store) == "env-token"


def test_header_token_beats_profile_and_env() -> None:
    """X-HH-Token приоритетнее OAuth-профиля и env."""
    store = TokenStore()
    store.save_tokens("default", "oauth-token", None)
    config = make_config(token="env-token")
    request_context.set_request_auth(hh_token="header-token", profile="default")
    assert resolve_hh_token(config, store) == "header-token"


def test_profile_token_beats_env() -> None:
    """Токен OAuth-профиля приоритетнее env HH_TOKEN (порядок плана M7)."""
    store = TokenStore()
    store.save_tokens("default", "oauth-token", None)
    config = make_config(token="env-token")
    assert resolve_hh_token(config, store) == "oauth-token"


def test_env_disabled_when_api_keys_configured() -> None:
    """При заданных MCP_API_KEYS env HH_TOKEN игнорируется (изоляция)."""
    store = TokenStore()
    config = make_config(token="env-token", api_keys=("key-a",))
    # Профиль запроса пользователя key-a пуст, env отключён -> токена нет.
    request_context.set_request_auth(
        hh_token=None, profile=profile_key_from_api_key("key-a")
    )
    assert resolve_hh_token(config, store) is None

    # Без контекста (stdio) и с api_keys env тоже отключён.
    request_context.set_request_auth(hh_token=None, profile=None)
    assert resolve_hh_token(config, store) is None


def test_profile_isolation_between_users() -> None:
    """Токен пользователя A недоступен в запросе пользователя B."""
    store = TokenStore()
    profile_a = profile_key_from_api_key("key-a")
    profile_b = profile_key_from_api_key("key-b")
    store.save_tokens(profile_a, "token-a", None)

    config = make_config(api_keys=("key-a", "key-b"))
    request_context.set_request_auth(hh_token=None, profile=profile_b)
    assert resolve_hh_token(config, store) is None  # у B токена нет.

    request_context.set_request_auth(hh_token=None, profile=profile_a)
    assert resolve_hh_token(config, store) == "token-a"


def test_profiles_are_sha256_of_api_keys() -> None:
    """Ключ профиля – sha256 API-ключа; сырой ключ в базе не хранится."""
    store = TokenStore()
    key = "key-a"
    profile = profile_key_from_api_key(key)
    assert profile != key
    assert len(profile) == 64  # hex sha256
    store.save_tokens(profile, "token-a", None)
    rows = store._conn.execute("SELECT profile_key FROM profiles").fetchall()  # noqa: SLF001
    assert all(key not in row["profile_key"] for row in rows)


async def test_token_provider_uses_request_profile() -> None:
    """TokenProvider.ensure_fresh работает с профилем запроса, не default."""
    store = TokenStore()
    profile_a = profile_key_from_api_key("key-a")
    store.save_tokens(profile_a, "token-a", None)
    config = make_config(api_keys=("key-a",))

    seen: list[str] = []

    async def do_request(token: str) -> str:
        seen.append(token)
        return "ok"

    provider = TokenProvider(config, store)
    # Контекст запроса пользователя A: auth_tools передаёт DEFAULT_PROFILE,
    # провайдер подменяет его профилем запроса.
    request_context.set_request_auth(hh_token=None, profile=profile_a)
    assert await provider.ensure_fresh(do_request) == "ok"
    assert seen == ["token-a"]


async def test_token_provider_no_token_error_hint() -> None:
    """Без токена – структурированная ошибка с подсказкой."""
    store = TokenStore()
    config = make_config(api_keys=("key-a",), token="env-token")
    request_context.set_request_auth(
        hh_token=None, profile=profile_key_from_api_key("key-a")
    )
    provider = TokenProvider(config, store)

    async def do_request(token: str) -> str:  # pragma: no cover - не вызовется
        return token

    with pytest.raises(HHError) as excinfo:
        await provider.ensure_fresh(do_request)
    assert excinfo.value.code == "no_hh_token"
    assert "X-HH-Token" in (excinfo.value.hint or "")


# --- ветки обмена/обновления токена (HHOAuth) --------------------------------


async def test_exchange_rejects_non_dict_token_response() -> None:
    """Ответ /token – не JSON-объект: oauth_bad_response."""
    store = TokenStore()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[1, 2]))
    oauth = HHOAuth(_oauth_config(), store, transport=transport)  # type: ignore[arg-type]
    with pytest.raises(HHError) as excinfo:
        await oauth.exchange_code("CODE")
    assert excinfo.value.code == "oauth_bad_response"


async def test_exchange_error_status_with_non_json_body() -> None:
    """/token ответил 400 с не-JSON телом – HHError по статусу."""
    store = TokenStore()
    transport = httpx.MockTransport(lambda request: httpx.Response(400, text="bad"))
    oauth = HHOAuth(_oauth_config(), store, transport=transport)  # type: ignore[arg-type]
    with pytest.raises(HHError) as excinfo:
        await oauth.exchange_code("CODE")
    assert excinfo.value.code == "bad_request"


async def test_exchange_requires_access_token_in_response() -> None:
    store = TokenStore()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"refresh_token": "RT"})
    )
    oauth = HHOAuth(_oauth_config(), store, transport=transport)  # type: ignore[arg-type]
    with pytest.raises(HHError, match="access_token"):
        await oauth.exchange_code("CODE")


async def test_exchange_drops_non_string_refresh_token() -> None:
    """refresh_token не-строкового типа отбрасывается (None)."""
    store = TokenStore()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"access_token": "AT", "refresh_token": 123}
        )
    )
    oauth = HHOAuth(_oauth_config(), store, transport=transport)  # type: ignore[arg-type]
    stored = await oauth.exchange_code("CODE")
    assert stored.access_token == "AT"
    assert stored.refresh_token is None


# --- ensure_fresh: неудачный и бесполезный refresh ---------------------------


async def test_ensure_fresh_refresh_failure_raises_original_401() -> None:
    """Refresh не удался – наружу исходная ошибка unauthorized."""
    store = TokenStore()
    store.save_tokens("default", "AT-old", "RT-old")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/token"
        return httpx.Response(400, json={"errors": [{"type": "oauth"}]})

    provider = TokenProvider(make_config(), store, transport=httpx.MockTransport(handler))
    calls: list[str] = []

    async def do_request(token: str) -> str:
        calls.append(token)
        raise HHError("unauthorized", "401 от hh.ru")

    with pytest.raises(HHError) as excinfo:
        await provider.ensure_fresh(do_request)
    assert excinfo.value.code == "unauthorized"
    assert calls == ["AT-old"]


async def test_ensure_fresh_same_token_after_refresh_raises_original() -> None:
    """Refresh вернул тот же токен – повтор бессмыслен, исходная 401."""
    store = TokenStore()
    store.save_tokens("default", "AT-same", "RT-old")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"access_token": "AT-same", "refresh_token": "RT-new"}
        )

    provider = TokenProvider(make_config(), store, transport=httpx.MockTransport(handler))
    calls: list[str] = []

    async def do_request(token: str) -> str:
        calls.append(token)
        raise HHError("unauthorized", "401 от hh.ru")

    with pytest.raises(HHError) as excinfo:
        await provider.ensure_fresh(do_request)
    assert excinfo.value.code == "unauthorized"
    assert calls == ["AT-same"]
