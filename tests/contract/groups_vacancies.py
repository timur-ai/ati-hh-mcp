"""Группа покрытия «vacancies» для метатеста (M3a).

Формат файла группы – см. tests/contract/groups_dictionaries.py.
"""

from __future__ import annotations

TOOLSET: str = "vacancies"

REQUIRES_AUTH: bool = False

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/vacancies"),
    ("GET", "/vacancies/{vacancy_id}"),
    ("GET", "/vacancies/{vacancy_id}/similar_vacancies"),
    ("GET", "/vacancies/{vacancy_id}/related_vacancies"),
}
