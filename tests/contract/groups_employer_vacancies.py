"""Группа покрытия «employer_vacancies» (этап M3c, воркер 1).

Формат файла группы – см. tests/contract/groups_dictionaries.py.
"""

from __future__ import annotations

TOOLSET: str = "employer_vacancies"

REQUIRES_AUTH: bool = True

OPERATIONS: set[tuple[str, str]] = {
    ("POST", "/vacancies"),
    ("PUT", "/vacancies/{vacancy_id}"),
    ("GET", "/vacancies/{vacancy_id}/prolongate"),
    ("POST", "/vacancies/{vacancy_id}/prolongate"),
    ("GET", "/employers/{employer_id}/vacancies/active"),
    ("GET", "/employers/{employer_id}/vacancies/archived"),
    ("PUT", "/employers/{employer_id}/vacancies/archived/{vacancy_id}"),
    ("GET", "/employers/{employer_id}/vacancies/hidden"),
    ("PUT", "/employers/{employer_id}/vacancies/hidden/{vacancy_id}"),
    ("DELETE", "/employers/{employer_id}/vacancies/hidden/{vacancy_id}"),
    ("GET", "/vacancies/drafts"),
    ("POST", "/vacancies/drafts"),
    ("GET", "/vacancies/drafts/{draft_id}"),
    ("PUT", "/vacancies/drafts/{draft_id}"),
    ("DELETE", "/vacancies/drafts/{draft_id}"),
    ("POST", "/vacancies/drafts/{draft_id}/publish"),
    ("GET", "/vacancies/drafts/{draft_id}/duplicates"),
    ("DELETE", "/vacancies/auto_publication"),
    ("GET", "/vacancies/{id}/preferred_negotiations_order"),
    ("PUT", "/vacancies/{id}/preferred_negotiations_order"),
    ("GET", "/vacancies/{vacancy_id}/stats"),
    ("GET", "/vacancies/{vacancy_id}/visitors"),
    ("GET", "/vacancies/{vacancy_id}/upgrades"),
}
