"""Юнит-тесты хранилища OAuth-токенов (SQLite, stdlib)."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from ati_hh_mcp.hh.token_store import (
    DEFAULT_PROFILE,
    StoredTokens,
    TokenStore,
    profile_key_from_api_key,
)


def test_save_and_get_roundtrip(tmp_path: Path) -> None:
    store = TokenStore(f"{tmp_path}/tokens.db")
    try:
        saved = store.save_tokens("default", "AT", "RT")
        assert saved.access_token == "AT"
        assert saved.refresh_token == "RT"
        assert saved.obtained_at == saved.updated_at

        tokens = store.get_tokens("default")
        assert tokens == StoredTokens(
            access_token="AT",
            refresh_token="RT",
            obtained_at=saved.obtained_at,
            updated_at=saved.updated_at,
        )
    finally:
        store.close()


def test_get_missing_profile_returns_none() -> None:
    store = TokenStore()
    try:
        assert store.get_tokens("nobody") is None
    finally:
        store.close()


def test_update_preserves_obtained_at() -> None:
    store = TokenStore()
    try:
        first = store.save_tokens("default", "AT1", "RT1")
        second = store.save_tokens("default", "AT2", "RT2")
        assert second.access_token == "AT2"
        assert second.obtained_at == first.obtained_at
        assert second.updated_at >= first.updated_at
    finally:
        store.close()


def test_delete_profile() -> None:
    store = TokenStore()
    try:
        store.save_tokens("default", "AT", "RT")
        assert store.delete_profile("default") is True
        assert store.get_tokens("default") is None
        assert store.delete_profile("default") is False
    finally:
        store.close()


def test_profile_isolation() -> None:
    """Профиль A не видит токены профиля B."""
    store = TokenStore()
    try:
        store.save_tokens("profile-a", "AT-A", "RT-A")
        store.save_tokens("profile-b", "AT-B", "RT-B")
        assert store.get_tokens("profile-a").access_token == "AT-A"
        assert store.get_tokens("profile-b").access_token == "AT-B"
        store.delete_profile("profile-a")
        assert store.get_tokens("profile-a") is None
        assert store.get_tokens("profile-b") is not None
    finally:
        store.close()


def test_refresh_token_may_be_none() -> None:
    store = TokenStore()
    try:
        store.save_tokens("default", "AT", None)
        assert store.get_tokens("default").refresh_token is None
    finally:
        store.close()


def test_profile_key_from_api_key() -> None:
    """Ключ профиля – sha256-хэш; сырой ключ не используется напрямую."""
    key = profile_key_from_api_key("mcp-secret-key")
    assert key == hashlib.sha256(b"mcp-secret-key").hexdigest()
    assert len(key) == 64
    assert profile_key_from_api_key("mcp-secret-key") == key
    assert profile_key_from_api_key("other") != key
    assert DEFAULT_PROFILE == "default"


def test_sign_and_verify_state_roundtrip() -> None:
    store = TokenStore()
    try:
        state = store.sign_state("default")
        assert state.startswith("default|")
        assert store.verify_state(state) == "default"

        other = store.sign_state("a" * 64)
        assert other != state
        assert store.verify_state(other) == "a" * 64
    finally:
        store.close()


def test_verify_state_tampering_returns_none() -> None:
    store = TokenStore()
    try:
        state = store.sign_state("default")
        profile, _, signature = state.rpartition(".")

        # Подделка подписи.
        tampered_sig = f"default.{signature[:-2]}ff"
        assert store.verify_state(tampered_sig) is None
        # Подделка профиля (подпись чужая).
        tampered_profile = f"evil.{signature}"
        assert store.verify_state(tampered_profile) is None
        # Мусорные значения.
        assert store.verify_state("no-dot-here") is None
        assert store.verify_state("") is None
        assert store.verify_state(".") is None
    finally:
        store.close()


def test_secret_is_stable_within_store() -> None:
    store = TokenStore()
    try:
        first = store.ensure_secret()
        assert first
        assert store.ensure_secret() == first
    finally:
        store.close()


def test_secret_persists_between_openings(tmp_path: Path) -> None:
    """server_secret и токены переживают закрытие/открытие базы."""
    path = f"{tmp_path}/tokens.db"
    store = TokenStore(path)
    secret = store.ensure_secret()
    state = store.sign_state("default")
    store.save_tokens("default", "AT", "RT")
    store.close()

    reopened = TokenStore(path)
    try:
        assert reopened.ensure_secret() == secret
        assert reopened.verify_state(state) == "default"
        assert reopened.get_tokens("default").access_token == "AT"
    finally:
        reopened.close()


def test_wal_mode_for_file_database(tmp_path: Path) -> None:
    store = TokenStore(f"{tmp_path}/wal.db")
    try:
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        store.close()


def test_context_manager_closes() -> None:
    with TokenStore() as store:
        store.save_tokens("default", "AT", "RT")
    with pytest.raises(sqlite3.ProgrammingError):
        store.get_tokens("default")


# --- TTL подписи OAuth-state и права файла (team-fix LOW) ---------------------


def test_state_fresh_is_accepted(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "ttl.db")
    try:
        state = store.sign_state("default")
        assert store.verify_state(state) == "default"
    finally:
        store.close()


def test_state_expired_returns_none(tmp_path: Path) -> None:
    """Подпись старше STATE_TTL_SECONDS отклоняется (вставка старого ts)."""
    import time as time_module

    from ati_hh_mcp.hh.token_store import STATE_TTL_SECONDS

    store = TokenStore(tmp_path / "ttl-old.db")
    try:
        old_payload = f"default|{int(time_module.time()) - STATE_TTL_SECONDS - 10}"
        secret = store.ensure_secret().encode("utf-8")
        import hashlib
        import hmac as hmac_module

        signature = hmac_module.new(
            secret, old_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert store.verify_state(f"{old_payload}.{signature}") is None
    finally:
        store.close()


def test_state_from_the_future_returns_none(tmp_path: Path) -> None:
    """Подпись «из будущего» (сдвиг часов) тоже отклоняется."""
    import hashlib
    import hmac as hmac_module
    import time as time_module

    store = TokenStore(tmp_path / "ttl-future.db")
    try:
        future_payload = f"default|{int(time_module.time()) + 3600}"
        secret = store.ensure_secret().encode("utf-8")
        signature = hmac_module.new(
            secret, future_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert store.verify_state(f"{future_payload}.{signature}") is None
    finally:
        store.close()


def test_state_payload_without_timestamp_rejected(tmp_path: Path) -> None:
    """Legacy-формат без метки времени не проходит проверку TTL."""
    import hashlib
    import hmac as hmac_module

    store = TokenStore(tmp_path / "ttl-legacy.db")
    try:
        secret = store.ensure_secret().encode("utf-8")
        signature = hmac_module.new(
            secret, b"default", hashlib.sha256
        ).hexdigest()
        assert store.verify_state(f"default.{signature}") is None
    finally:
        store.close()


def test_database_file_permissions_0600(tmp_path: Path) -> None:
    """Файл базы (и wal/shm при наличии) доступен только владельцу."""
    import stat

    db_path = tmp_path / "perm.db"
    store = TokenStore(db_path)
    try:
        store.save_tokens("default", "AT", "RT")
        store._conn.execute("SELECT 1").fetchone()  # noqa: SLF001 – wal создаётся
        store._restrict_permissions()
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(db_path) + suffix)
            if candidate.exists():
                assert stat.S_IMODE(candidate.stat().st_mode) == 0o600, suffix
    finally:
        store.close()
