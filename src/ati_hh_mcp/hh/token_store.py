"""Хранилище OAuth-токенов hh.ru в SQLite (только stdlib).

Профиль – sha256-хэш API-ключа MCP (сырой ключ в базе не хранится) или
литерал ``default`` для персонального запуска без API-ключей. Кроме пар
токенов база хранит ``server_secret`` для подписи OAuth-state (генерируется
``secrets.token_urlsafe`` при первом создании и живёт в таблице meta).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

#: Имя единственного профиля, когда MCP_API_KEYS не заданы (stdio / простой HTTP).
DEFAULT_PROFILE = "default"

_META_SECRET_KEY = "server_secret"


@dataclass(frozen=True)
class StoredTokens:
    """Пара токенов одного профиля с метками времени (unixtime)."""

    access_token: str
    refresh_token: str | None
    obtained_at: float
    updated_at: float


def profile_key_from_api_key(api_key: str) -> str:
    """Ключ профиля из API-ключа MCP: sha256-хэш (hex), без сырого секрета."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


class TokenStore:
    """SQLite-хранилище пар токенов по профилям.

    База открывается в режиме WAL; атрибут :attr:`lock` (``asyncio.Lock``)
    оборачивает refresh-критические секции в :mod:`ati_hh_mcp.hh.auth`,
    чтобы параллельные запросы не обновили одну пару дважды.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Для :memory: прагма молча останется в режиме memory – это нормально.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS profiles ("
            "profile_key TEXT PRIMARY KEY, "
            "access_token TEXT NOT NULL, "
            "refresh_token TEXT, "
            "obtained_at REAL NOT NULL, "
            "updated_at REAL NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()
        #: Сериализация refresh-критических секций OAuth.
        self.lock = asyncio.Lock()

    @property
    def path(self) -> str:
        """Путь к файлу базы (для диагностики)."""
        return self._path

    # ------------------------------------------------------------------
    # Профили токенов
    # ------------------------------------------------------------------
    def get_tokens(self, profile_key: str) -> StoredTokens | None:
        """Возвращает пару токенов профиля или None, если профиля нет."""
        row = self._conn.execute(
            "SELECT access_token, refresh_token, obtained_at, updated_at "
            "FROM profiles WHERE profile_key = ?",
            (profile_key,),
        ).fetchone()
        if row is None:
            return None
        return StoredTokens(
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            obtained_at=row["obtained_at"],
            updated_at=row["updated_at"],
        )

    def save_tokens(
        self,
        profile_key: str,
        access_token: str,
        refresh_token: str | None,
    ) -> StoredTokens:
        """Сохраняет пару токенов; obtained_at сохраняется при обновлении."""
        now = time.time()
        existing = self.get_tokens(profile_key)
        obtained_at = existing.obtained_at if existing is not None else now
        self._conn.execute(
            "INSERT INTO profiles "
            "(profile_key, access_token, refresh_token, obtained_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(profile_key) DO UPDATE SET "
            "access_token = excluded.access_token, "
            "refresh_token = excluded.refresh_token, "
            "updated_at = excluded.updated_at",
            (profile_key, access_token, refresh_token, obtained_at, now),
        )
        self._conn.commit()
        return StoredTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            obtained_at=obtained_at,
            updated_at=now,
        )

    def delete_profile(self, profile_key: str) -> bool:
        """Удаляет профиль; True – профиль существовал."""
        cursor = self._conn.execute(
            "DELETE FROM profiles WHERE profile_key = ?", (profile_key,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Секрет сервера и подпись OAuth-state
    # ------------------------------------------------------------------
    def ensure_secret(self) -> str:
        """Возвращает server_secret, генерируя его при первом обращении."""
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (_META_SECRET_KEY,)
        ).fetchone()
        if row is not None:
            return str(row["value"])
        secret = secrets.token_urlsafe(32)
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            (_META_SECRET_KEY, secret),
        )
        self._conn.commit()
        return secret

    def sign_state(self, profile_key: str) -> str:
        """Подписывает профиль для OAuth-state: ``"<profile>.<sig>"``."""
        secret = self.ensure_secret().encode("utf-8")
        signature = hmac.new(secret, profile_key.encode("utf-8"), "sha256").hexdigest()
        return f"{profile_key}.{signature}"

    def verify_state(self, state: str) -> str | None:
        """Проверяет подпись state; возвращает профиль или None при подделке."""
        profile_key, separator, signature = state.rpartition(".")
        if not separator or not profile_key:
            return None
        secret = self.ensure_secret().encode("utf-8")
        expected = hmac.new(secret, profile_key.encode("utf-8"), "sha256").hexdigest()
        if hmac.compare_digest(expected, signature):
            return profile_key
        return None

    # ------------------------------------------------------------------
    # Закрытие
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Закрывает соединение с базой."""
        self._conn.close()

    def __enter__(self) -> TokenStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
