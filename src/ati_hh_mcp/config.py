"""Конфигурация сервера из переменных окружения."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

# Наборы инструментов, включённые по умолчанию (план, «Группировка наборов»).
DEFAULT_TOOLSETS: tuple[str, ...] = (
    "auth",
    "dictionaries",
    "suggests",
    "vacancies",
    "negotiations",
    "chats",
    "resumes",
)

DEFAULT_API_BASE = "https://api.hh.ru"

# Лимит запросов к API hh.ru в минуту (троттлинг, этап M2).
DEFAULT_RATE_LIMIT = 25

# Требование hh.ru к User-Agent: владелец развёртывания должен указать свой
# контактный email (HH_UA_EMAIL); значение ниже – только явный placeholder.
DEFAULT_UA_EMAIL = "unknown@example.com"


def _split_csv(raw: str | None) -> tuple[str, ...]:
    """Разбор строки через запятую в кортеж непустых значений."""
    if not raw:
        return ()
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def _clean(raw: str | None) -> str | None:
    """Убирает пробелы; пустая строка считается отсутствием значения."""
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _parse_int(raw: str | None, default: int) -> int:
    """Разбирает целое из env; некорректное значение откатывается к дефолту."""
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    """Иммутабельная конфигурация, собранная из окружения."""

    token: str | None
    toolsets: tuple[str, ...]
    api_base: str
    ua_email: str
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    api_keys: tuple[str, ...]
    rate_limit: int = field(default=DEFAULT_RATE_LIMIT)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        """Собирает конфигурацию из env (по умолчанию – os.environ)."""
        source: Mapping[str, str] = os.environ if env is None else env

        toolsets_raw = _clean(source.get("HH_TOOLSETS"))
        api_base = _clean(source.get("HH_API_BASE")) or DEFAULT_API_BASE
        ua_email = _clean(source.get("HH_UA_EMAIL")) or DEFAULT_UA_EMAIL
        rate_limit = _parse_int(_clean(source.get("HH_RATE_LIMIT")), DEFAULT_RATE_LIMIT)
        if rate_limit <= 0:
            # Нулевой или отрицательный лимит заблокировал бы все запросы.
            rate_limit = DEFAULT_RATE_LIMIT

        return cls(
            token=_clean(source.get("HH_TOKEN")),
            toolsets=_split_csv(toolsets_raw) or DEFAULT_TOOLSETS,
            api_base=api_base.rstrip("/"),
            ua_email=ua_email,
            client_id=_clean(source.get("HH_CLIENT_ID")),
            client_secret=_clean(source.get("HH_CLIENT_SECRET")),
            redirect_uri=_clean(source.get("HH_REDIRECT_URI")),
            api_keys=_split_csv(source.get("MCP_API_KEYS")),
            rate_limit=rate_limit,
        )

    def with_toolsets(self, toolsets: tuple[str, ...]) -> Config:
        """Копия конфигурации с другим набором toolsets (override CLI)."""
        return replace(self, toolsets=tuple(name.lower() for name in toolsets))
