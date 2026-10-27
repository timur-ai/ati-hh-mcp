"""Группа покрытия «employer_misc» (волна 3, M3d-Ч2).

Необязательные атрибуты (введены волной M3d-Ч2, см. докстринг
``tests/contract/test_coverage.py``):
- ``POST_NON_MUTATIONS`` – POST-операции, семантически являющиеся
  чтением (``is_mutation=False``, без confirm): POST-поиски звонков;
- ``PUBLIC_OPERATIONS`` – операции без токена hh.ru внутри группы с
  ``requires_auth=True``: поиск/просмотр работодателей и четыре
  справочника зарплатной статистики.
"""

from __future__ import annotations

TOOLSET: str = "employer_misc"

OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/employers"),
    ("GET", "/employers/{employer_id}"),
    ("GET", "/employers/{employer_id}/addresses"),
    ("GET", "/employers/{employer_id}/addresses/{address_id}"),
    ("GET", "/employers/{employer_id}/departments"),
    ("GET", "/employers/{employer_id}/services/payable_api_actions/active"),
    ("GET", "/employers/{employer_id}/services/available_publications"),
    ("GET", "/employers/{employer_id}/tests"),
    ("GET", "/employers/{employer_id}/vacancy_branded_templates"),
    ("GET", "/employers/{employer_id}/vacancy_areas/active"),
    ("GET", "/calls/history"),
    ("GET", "/calls/link"),
    ("POST", "/calls/records/search"),
    ("POST", "/calls/transcripts/search"),
    ("GET", "/clickme/statistics"),
    ("GET", "/webhook/subscriptions"),
    ("POST", "/webhook/subscriptions"),
    ("PUT", "/webhook/subscriptions/{subscription_id}"),
    ("DELETE", "/webhook/subscriptions/{subscription_id}"),
    ("GET", "/salary_statistics/dictionaries/salary_industries"),
    ("GET", "/salary_statistics/dictionaries/professional_areas"),
    ("GET", "/salary_statistics/dictionaries/employee_levels"),
    ("GET", "/salary_statistics/dictionaries/salary_areas"),
    ("GET", "/salary_statistics/paid/salary_evaluation/{area_id}"),
    ("GET", "/message_templates/{template}"),
}

POST_NON_MUTATIONS: set[tuple[str, str]] = {
    ("POST", "/calls/records/search"),
    ("POST", "/calls/transcripts/search"),
}

PUBLIC_OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/employers"),
    ("GET", "/employers/{employer_id}"),
    ("GET", "/salary_statistics/dictionaries/salary_industries"),
    ("GET", "/salary_statistics/dictionaries/professional_areas"),
    ("GET", "/salary_statistics/dictionaries/employee_levels"),
    ("GET", "/salary_statistics/dictionaries/salary_areas"),
}
