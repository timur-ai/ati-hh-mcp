"""Группа покрытия «dictionaries» для метатеста (M3a).

Формат файла группы (автоподхват tests/contract/test_coverage.py):
- ``TOOLSET: str`` – имя набора инструментов;
- ``OPERATIONS: set[tuple[str, str]]`` – операции вендор-спеки
  (метод, путь), покрываемые набором 1:1;
- ``REQUIRES_AUTH: bool`` (по умолчанию True) – нужен ли всем
  инструментам набора токен hh.ru;
- ``MODULE: str`` (по умолчанию ``ati_hh_mcp.toolsets.<TOOLSET>``) –
  путь модуля набора; указывается только при несовпадении имён
  (например, auth -> auth_tools).
"""

from __future__ import annotations

TOOLSET: str = "dictionaries"

REQUIRES_AUTH: bool = False

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/dictionaries"),
    ("GET", "/areas"),
    ("GET", "/areas/countries"),
    ("GET", "/areas/{area_id}"),
    ("GET", "/industries"),
    ("GET", "/professional_roles"),
    ("GET", "/languages"),
    ("GET", "/locales"),
    ("GET", "/locales/resume"),
    ("GET", "/districts"),
    ("GET", "/metro"),
    ("GET", "/metro/{city_id}"),
    ("GET", "/skills"),
    ("GET", "/educational_institutions"),
    ("GET", "/educational_institutions/{id}/faculties"),
    ("GET", "/vacancy_conditions"),
}
