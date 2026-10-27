"""Тесты разбора конфигурации из окружения."""

from __future__ import annotations

from ati_hh_mcp.config import (
    DEFAULT_API_BASE,
    DEFAULT_TOOLSETS,
    DEFAULT_UA_EMAIL,
    Config,
)


def test_defaults_when_env_empty() -> None:
    config = Config.from_env(env={})
    assert config.token is None
    assert config.toolsets == DEFAULT_TOOLSETS
    assert config.api_base == DEFAULT_API_BASE
    assert config.ua_email == DEFAULT_UA_EMAIL
    assert config.client_id is None
    assert config.client_secret is None
    assert config.redirect_uri is None
    assert config.api_keys == ()


def test_token_and_email() -> None:
    config = Config.from_env(env={"HH_TOKEN": " t0ken ", "HH_UA_EMAIL": "me@example.com"})
    assert config.token == "t0ken"
    assert config.ua_email == "me@example.com"


def test_empty_values_fall_back_to_defaults() -> None:
    config = Config.from_env(env={"HH_TOKEN": "   ", "HH_API_BASE": ""})
    assert config.token is None
    assert config.api_base == DEFAULT_API_BASE


def test_toolsets_csv_parsing() -> None:
    config = Config.from_env(env={"HH_TOOLSETS": " Dictionaries , vacancies ,extended "})
    assert config.toolsets == ("dictionaries", "vacancies", "extended")


def test_toolsets_empty_falls_back_to_default() -> None:
    config = Config.from_env(env={"HH_TOOLSETS": " , "})
    assert config.toolsets == DEFAULT_TOOLSETS


def test_api_base_trailing_slash_stripped() -> None:
    config = Config.from_env(env={"HH_API_BASE": "https://api.hh.test/"})
    assert config.api_base == "https://api.hh.test"


def test_oauth_and_api_keys() -> None:
    config = Config.from_env(
        env={
            "HH_CLIENT_ID": "cid",
            "HH_CLIENT_SECRET": "secret",
            "HH_REDIRECT_URI": "https://example.com/callback",
            "MCP_API_KEYS": " key1 , key2 ",
        }
    )
    assert config.client_id == "cid"
    assert config.client_secret == "secret"
    assert config.redirect_uri == "https://example.com/callback"
    assert config.api_keys == ("key1", "key2")


def test_with_toolsets_override() -> None:
    config = Config.from_env(env={})
    overridden = config.with_toolsets(("Vacancies", "Extended"))
    assert overridden.toolsets == ("vacancies", "extended")
    # Исходная конфигурация не изменилась (иммутабельность).
    assert config.toolsets == DEFAULT_TOOLSETS
