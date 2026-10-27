"""Хранилище OAuth-токенов hh.ru в SQLite (только stdlib).

Профиль – sha256-хэш API-ключа MCP (сырой ключ в базе не хранится) или
литерал ``default`` для персонального запуска без API-ключей. Кроме пар
токенов база хранит ``server_secret`` для подписи OAuth-state (генерируется
``secrets.token_urlsafe`` при первом создании и живёт в таблице meta);
state подписывается с меткой времени и живёт не дольше ``STATE_TTL_SECONDS``.

Ограничение модели: sqlite3 синхронный, а сервер асинхронный. Допустимо
при одном worker-процессе uvicorn (короткие локальные транзакции, режим
WAL); файл базы располагайте на локальной ФС – на сетевой файловой системе
перенесите вызовы в ``asyncio.to_thread``.

Файл базы (и ``-wal``/``-shm``, если уже созданы) получает права 0o600:
внутри – токены hh.ru.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

#: Имя единственного профиля, когда MCP_API_KEYS не заданы (stdio / простой HTTP).
DEFAULT_PROFILE = "default"

_META_SECRET_KEY = "server_secret"

#: Срок жизни подписи OAuth-state (24 часа).
STATE_TTL_SECONDS = 24 * 60 * 60


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
        self._restrict_permissions()
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

    def _restrict_permissions(self) -> None:
        """Права 0o600 на файл базы и wal/shm-файлы, если они есть.

        Внутри базы – токены hh.ru; доступ только владельцу. Для
        ``:memory:`` и недоступного пути шаг молча пропускается
        (диагностика прав не входит в контракт хранилища).
        """
        for suffix in ("", "-wal", "-shm"):
            candidate = self._path + suffix
            try:
                os.chmod(candidate, 0o600)
            except OSError:
                continue  # файла нет или :memory:.

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
        """Подписывает профиль для OAuth-state: ``"<profile>|<ts>.<sig>"``.

        Метка времени ограничивает срок жизни state значением
        ``STATE_TTL_SECONDS`` (24 часа): повторное использование старой
        ссылки входа после истечения срока отклоняется ``verify_state``.
        """
        payload = f"{profile_key}|{int(time.time())}"
        secret = self.ensure_secret().encode("utf-8")
        signature = hmac.new(secret, payload.encode("utf-8"), "sha256").hexdigest()
        return f"{payload}.{signature}"

    def verify_state(self, state: str) -> str | None:
        """Проверяет подпись и срок жизни state; профиль или None.

        None возвращается при подделке подписи, некорректном формате и
        возрасте подписи свыше ``STATE_TTL_SECONDS``.
        """
        payload, separator, signature = state.rpartition(".")
        if not separator or not payload:
            return None
        secret = self.ensure_secret().encode("utf-8")
        expected = hmac.new(secret, payload.encode("utf-8"), "sha256").hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        profile_key, pipe, ts_raw = payload.rpartition("|")
        if not pipe or not profile_key or not ts_raw.isdigit():
            return None
        age = time.time() - int(ts_raw)
        if age < 0 or age > STATE_TTL_SECONDS:
            return None  # просроченная или «из будущего» подпись.
        return profile_key

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
