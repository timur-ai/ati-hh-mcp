"""Операции набора «chats» для метатеста покрытия (волна 3, M3b)."""

from __future__ import annotations

TOOLSET: str = "chats"

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/common/chats"),
    ("GET", "/common/chats/counters/unread"),
    ("GET", "/common/chats/files/conditions"),
    ("POST", "/common/chats/files/upload_links"),
    ("POST", "/common/chats/without_vacancy"),
    ("PUT", "/common/chats/{chat_id}/leave"),
    ("PUT", "/common/chats/{chat_id}/message/{message_id}/read"),
    ("GET", "/common/chats/{chat_id}/messages"),
    ("POST", "/common/chats/{chat_id}/messages"),
    ("PUT", "/common/chats/{chat_id}/messages/{message_id}"),
    ("DELETE", "/common/chats/{chat_id}/messages/{message_id}"),
    ("GET", "/common/chats/{chat_id}/participants"),
    ("PUT", "/common/chats/{chat_id}/participants"),
    ("PUT", "/common/chats/{chat_id}/write_possibility"),
}
