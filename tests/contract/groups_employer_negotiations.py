"""Группа покрытия «employer_negotiations» (этап M3c, воркер 1).

Включает операцию GET /resumes/{resume_id}/negotiations_history
(история откликов по резюме – сторона работодателя) по распределению
операций волны 3, а не по эскизу архитектуры плана (там она в resumes).

Формат файла группы – см. tests/contract/groups_dictionaries.py.
"""

from __future__ import annotations

TOOLSET: str = "employer_negotiations"

REQUIRES_AUTH: bool = True

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/employers/{employer_id}/mail_templates"),
    ("PUT", "/employers/{employer_id}/mail_templates/{template_id}"),
    ("GET", "/resumes/{resume_id}/negotiations_history"),
    ("GET", "/employers/{employer_id}/negotiations_statistics"),
    (
        "GET",
        "/employers/{employer_id}/managers/{manager_id}/negotiations_statistics",
    ),
}
