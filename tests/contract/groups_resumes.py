"""Операции набора «resumes» для метатеста покрытия (волна 3, M3b)."""

from __future__ import annotations

TOOLSET: str = "resumes"

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/resumes/{resume_id}"),
    ("GET", "/resumes/{resume_id}/phone"),
}
