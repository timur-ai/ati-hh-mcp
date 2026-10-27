"""Группа покрытия «auth» для метатеста (M5-модули).

Операции из 135, покрытые инструментами; служебные auth_get_login_url/
auth_exchange_code/auth_status – плейсхолдеры ``INTERNAL auth:*`` вне 135
и в множество группы не входят. Формат файла группы – см.
tests/contract/groups_dictionaries.py.
"""

from __future__ import annotations

TOOLSET: str = "auth"

REQUIRES_AUTH: bool = True

#: Модуль набора не совпадает с именем по шаблону.
MODULE: str = "ati_hh_mcp.toolsets.auth_tools"

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/me"),
    ("DELETE", "/token"),
}
