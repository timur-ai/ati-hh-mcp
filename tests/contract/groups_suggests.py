"""Группа покрытия «suggests» для метатеста (M3a).

Формат файла группы – см. tests/contract/groups_dictionaries.py.
"""

from __future__ import annotations

TOOLSET: str = "suggests"

REQUIRES_AUTH: bool = False

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/suggests/areas"),
    ("GET", "/suggests/area_leaves"),
    ("GET", "/suggests/companies"),
    ("GET", "/suggests/educational_institutions"),
    ("GET", "/suggests/fields_of_study"),
    ("GET", "/suggests/positions"),
    ("GET", "/suggests/professional_roles"),
    ("GET", "/suggests/resume_search_keyword"),
    ("GET", "/suggests/skill_set"),
    ("GET", "/suggests/vacancy_positions"),
    ("GET", "/suggests/vacancy_search_keyword"),
}
