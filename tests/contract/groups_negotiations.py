"""Операции набора «negotiations» для метатеста покрытия (волна 3, M3b)."""

from __future__ import annotations

TOOLSET: str = "negotiations"

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/negotiations"),
    ("GET", "/negotiations/{id}"),
    ("PUT", "/negotiations/{id}"),
    ("PUT", "/negotiations/{collection_name}/{nid}"),
    ("GET", "/negotiations/{nid}/messages"),
    ("POST", "/negotiations/{nid}/messages"),
    ("GET", "/negotiations/response"),
    ("POST", "/negotiations/read"),
    ("POST", "/negotiations/phone_interview"),
    ("GET", "/negotiations/{nid}/test/solution"),
}
