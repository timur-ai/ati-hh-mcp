"""Операции набора «employer_resumes» (волна 3, M3d-Ч1).

Точный список операций вендорённой OpenAPI, покрываемых инструментами
набора; автоподхватывается контрактным метатестом покрытия.
"""

from __future__ import annotations

TOOLSET: str = "employer_resumes"

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/resumes"),
    ("GET", "/saved_searches/resumes"),
    ("POST", "/saved_searches/resumes"),
    ("GET", "/saved_searches/resumes/{id}"),
    ("PUT", "/saved_searches/resumes/{id}"),
    ("DELETE", "/saved_searches/resumes/{id}"),
    ("PUT", "/saved_searches/resumes/{saved_search_id}/managers/{manager_id}"),
    ("GET", "/applicant_comments/{applicant_id}"),
    ("POST", "/applicant_comments/{applicant_id}"),
    ("PUT", "/applicant_comments/{applicant_id}/{comment_id}"),
    ("DELETE", "/applicant_comments/{applicant_id}/{comment_id}"),
}
