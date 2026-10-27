"""Контекст HTTP-запроса: токен X-HH-Token и OAuth-профиль пользователя.

Middleware HTTP-транспорта (``server.RequestAuthMiddleware``) сохраняет
в ContextVar значения текущего запроса: заголовок ``X-HH-Token`` и ключ
профиля (sha256 валидированного API-ключа либо ``default`` в открытом
режиме). Клиентская фабрика и OAuth-слой читают их при построении
клиентов – каждый HTTP-запрос работает со своим токеном hh.ru.

В stdio-режиме middleware нет: переменные не заданы, ``effective_profile``
возвращает переданный fallback (обычно ``default``), поведение слоя
авторизации не меняется.
"""

from __future__ import annotations

from contextvars import ContextVar

from .hh.token_store import DEFAULT_PROFILE

_hh_token: ContextVar[str | None] = ContextVar("ati_hh_request_hh_token", default=None)
_profile: ContextVar[str | None] = ContextVar("ati_hh_request_profile", default=None)


def set_request_auth(*, hh_token: str | None, profile: str | None) -> None:
    """Задаёт контекст запроса (вызывается middleware один раз на запрос)."""
    _hh_token.set(hh_token or None)
    _profile.set(profile or None)


def get_request_hh_token() -> str | None:
    """Токен hh.ru из заголовка X-HH-Token текущего запроса (если задан)."""
    return _hh_token.get()


def get_request_profile() -> str | None:
    """Профиль текущего запроса; None – контекст не задан (stdio)."""
    return _profile.get()


def effective_profile(fallback: str = DEFAULT_PROFILE) -> str:
    """Профиль запроса, если задан, иначе fallback.

    HTTP-режим: профиль фиксирован middleware (sha256 API-ключа или
    ``default`` при открытых настройках); stdio – всегда fallback.
    """
    return _profile.get() or fallback
