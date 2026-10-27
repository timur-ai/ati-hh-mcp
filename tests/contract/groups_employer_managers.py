"""Операции набора «employer_managers» (волна 3, M3d-Ч1).

Точный список операций вендорённой OpenAPI, покрываемых инструментами
набора; автоподхватывается контрактным метатестом покрытия.
Статистика откликов менеджера (.../negotiations_statistics) относится
к набору employer_negotiations и здесь не входит.
"""

from __future__ import annotations

TOOLSET: str = "employer_managers"

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/employers/{employer_id}/managers"),
    ("POST", "/employers/{employer_id}/managers"),
    ("GET", "/employers/{employer_id}/managers/{manager_id}"),
    ("PUT", "/employers/{employer_id}/managers/{manager_id}"),
    ("DELETE", "/employers/{employer_id}/managers/{manager_id}"),
    ("GET", "/employers/{employer_id}/manager_types"),
    ("GET", "/employers/{employer_id}/managers/{manager_id}/limits/resume"),
    ("GET", "/employers/{employer_id}/managers/{manager_id}/method_access"),
    ("GET", "/employers/{employer_id}/managers/{manager_id}/settings"),
    (
        "GET",
        "/employers/{employer_id}/managers/{manager_id}/vacancies/available_types",
    ),
    ("GET", "/manager_accounts/mine"),
}
