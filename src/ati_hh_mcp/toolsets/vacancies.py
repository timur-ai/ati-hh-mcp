"""Набор «vacancies»: поиск и просмотр вакансий – 4 операции.

Тяжёлая операция ``GET /vacancies`` (45 параметров включая служебные)
реализована двухуровневой схемой (решение реестра, план M3a):
обязательные и частые параметры – на верхнем уровне инструмента, длинный
хвост – во вложенной модели ``advanced``; в HTTP-запрос попадают только
заданные поля. Аналогичная схема применена к similar/related vacancies.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "vacancies"

_ADVANCED_NOTE = (
    " Rare or niche filters are grouped into the nested `advanced` object: "
    "pass only the fields you need, unset fields are not sent."
)


class VacancySearchAdvanced(BaseModel):
    """Длинный хвост фильтров GET /vacancies (двухуровневая схема).

    В запрос попадают только заданные поля (None не отправляется).
    """

    date_from: str | None = Field(
        None, description="Search vacancies published from this date (YYYY-MM-DD or ISO datetime)."
    )
    date_to: str | None = Field(None, description="Search vacancies published up to this date.")
    top_lat: float | None = Field(None, description="Top latitude of the map bounding box.")
    bottom_lat: float | None = Field(None, description="Bottom latitude of the map bounding box.")
    left_lng: float | None = Field(None, description="Left longitude of the map bounding box.")
    right_lng: float | None = Field(None, description="Right longitude of the map bounding box.")
    sort_point_lat: float | None = Field(
        None, description="Latitude of the point for distance sorting."
    )
    sort_point_lng: float | None = Field(
        None, description="Longitude of the point for distance sorting."
    )
    clusters: bool | None = Field(None, description="Include facet clusters in the response.")
    describe_arguments: bool | None = Field(
        None, description="Include a description of search arguments."
    )
    no_magic: bool | None = Field(None, description="Disable magic search behaviour adjustments.")
    premium: bool | None = Field(None, description="Only premium vacancies.")
    responses_count_enabled: bool | None = Field(None, description="Include response counts.")
    part_time: str | None = Field(
        None, description="Part-time job filter (id from vacancy conditions dictionary)."
    )
    accept_temporary: bool | None = Field(None, description="Accept temporary jobs flag.")
    employment_form: str | None = Field(
        None,
        description="Employment form filter (e.g. primary, secondary, hybrid; from dictionary).",
    )
    work_schedule_by_days: str | None = Field(
        None, description="Work schedule by days filter (e.g. flexible, shift)."
    )
    working_hours: str | None = Field(
        None, description="Working hours filter (e.g. start_end, till_noon)."
    )
    work_format: str | None = Field(
        None, description="Work format filter (office, remote, hybrid)."
    )
    excluded_text: str | None = Field(None, description="Exclude vacancies containing this text.")
    education: str | None = Field(
        None, description="Required education level filter (e.g. secondary, higher)."
    )
    driver_license_types: str | None = Field(
        None, description="Driver license types filter (e.g. B, C)."
    )
    salary_frequency: str | None = Field(
        None, description="Salary payment frequency filter (from dictionary)."
    )
    salary_mode: str | None = Field(None, description="Salary mode filter (from dictionary).")


class VacancySearchParams(BaseModel):
    """GET /vacancies: частые параметры верхнего уровня + advanced-хвост."""

    text: str | None = Field(
        None, description="Free-text vacancy query (supports hh.ru search operators)."
    )
    area: str | None = Field(
        None, description="Region id or ids (comma-separated) from dict_areas."
    )
    metro: str | None = Field(None, description="Metro station id or ids (comma-separated).")
    professional_role: str | None = Field(
        None, description="Professional role id or ids (comma-separated)."
    )
    industry: str | None = Field(None, description="Industry id or ids (comma-separated).")
    employer_id: str | None = Field(None, description="Employer id or ids (comma-separated).")
    currency: str | None = Field(None, description="Salary currency code (e.g. RUR, USD).")
    salary: float | None = Field(
        None, description="Salary amount; combined with currency and only_with_salary."
    )
    only_with_salary: bool | None = Field(None, description="Only vacancies with a stated salary.")
    experience: str | None = Field(
        None, description="Experience filter: noExperience, between1And3, between3And6, moreThan6."
    )
    employment: str | None = Field(
        None, description="Employment filter id (probation, full, part, flyInFlyOut)."
    )
    schedule: str | None = Field(
        None, description="Schedule filter id (fullDay, shift, flexible, remote, flyInFlyOut)."
    )
    search_field: str | None = Field(
        None,
        description="Restrict text search to fields: name, description, employer_name.",
    )
    label: str | None = Field(
        None, description="Label filter: not_from_agency, accept_handicapped, oligarch and others."
    )
    period: int | None = Field(None, description="Limit search to the last N days (max 30).")
    order_by: str | None = Field(
        None,
        description="Result order: relevance, publication_time, salary_desc, salary_asc, distance.",
    )
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 100, default 20).")
    advanced: VacancySearchAdvanced | None = Field(
        None,
        description="Rare filters: date range, geo bounding box, work format details and more.",
    )


class VacancyIdParams(BaseModel):
    """GET /vacancies/{vacancy_id}: одна вакансия."""

    vacancy_id: str


class SimilarVacanciesAdvanced(BaseModel):
    """Длинный хвост фильтров similar/related vacancies."""

    date_from: str | None = Field(None, description="Search vacancies published from this date.")
    date_to: str | None = Field(None, description="Search vacancies published up to this date.")
    top_lat: float | None = Field(None, description="Top latitude of the map bounding box.")
    bottom_lat: float | None = Field(None, description="Bottom latitude of the map bounding box.")
    left_lng: float | None = Field(None, description="Left longitude of the map bounding box.")
    right_lng: float | None = Field(None, description="Right longitude of the map bounding box.")
    sort_point_lat: float | None = Field(
        None, description="Latitude of the point for distance sorting."
    )
    sort_point_lng: float | None = Field(
        None, description="Longitude of the point for distance sorting."
    )
    clusters: bool | None = Field(None, description="Include facet clusters in the response.")
    describe_arguments: bool | None = Field(
        None, description="Include a description of search arguments."
    )
    no_magic: bool | None = Field(None, description="Disable magic search behaviour adjustments.")
    premium: bool | None = Field(None, description="Only premium vacancies.")
    responses_count_enabled: bool | None = Field(None, description="Include response counts.")
    part_time: str | None = Field(
        None, description="Part-time job filter (id from vacancy conditions dictionary)."
    )
    employment_form: str | None = Field(
        None,
        description="Employment form filter (e.g. primary, secondary, hybrid; from dictionary).",
    )
    work_schedule_by_days: str | None = Field(
        None, description="Work schedule by days filter (e.g. flexible, shift)."
    )
    working_hours: str | None = Field(
        None, description="Working hours filter (e.g. start_end, till_noon)."
    )
    work_format: str | None = Field(
        None, description="Work format filter (office, remote, hybrid)."
    )
    education: str | None = Field(
        None, description="Required education level filter (e.g. secondary, higher)."
    )
    driver_license_types: str | None = Field(
        None, description="Driver license types filter (e.g. B, C)."
    )
    excluded_employer_id: str | None = Field(
        None, description="Exclude vacancies of these employer ids."
    )
    salary_frequency: str | None = Field(
        None, description="Salary payment frequency filter (from dictionary)."
    )
    salary_mode: str | None = Field(None, description="Salary mode filter (from dictionary).")


class SimilarVacanciesParams(BaseModel):
    """similar/related vacancies: vacancy_id + частые фильтры + advanced."""

    vacancy_id: str = Field(..., description="Source vacancy id.")
    text: str | None = Field(None, description="Free-text query to refine the suggestion.")
    area: str | None = Field(None, description="Region id or ids (comma-separated).")
    metro: str | None = Field(None, description="Metro station id or ids (comma-separated).")
    professional_role: str | None = Field(
        None, description="Professional role id or ids (comma-separated)."
    )
    industry: str | None = Field(None, description="Industry id or ids (comma-separated).")
    employer_id: str | None = Field(None, description="Employer id or ids (comma-separated).")
    currency: str | None = Field(None, description="Salary currency code (e.g. RUR, USD).")
    salary: float | None = Field(None, description="Salary amount filter.")
    only_with_salary: bool | None = Field(None, description="Only vacancies with a stated salary.")
    experience: str | None = Field(
        None, description="Experience filter: noExperience, between1And3, between3And6, moreThan6."
    )
    employment: str | None = Field(
        None, description="Employment filter id (probation, full, part, flyInFlyOut)."
    )
    schedule: str | None = Field(
        None, description="Schedule filter id (fullDay, shift, flexible, remote, flyInFlyOut)."
    )
    search_field: str | None = Field(
        None, description="Restrict text search to fields: name, description, employer_name."
    )
    label: str | None = Field(
        None, description="Label filter (not_from_agency, accept_handicapped and others)."
    )
    period: int | None = Field(None, description="Limit search to the last N days (max 30).")
    order_by: str | None = Field(
        None,
        description="Result order: relevance, publication_time, salary_desc, salary_asc, distance.",
    )
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 100).")
    advanced: SimilarVacanciesAdvanced | None = Field(
        None,
        description="Rare filters: date range, geo bounding box, work format details and more.",
    )


SEARCH_VACANCIES = make_tool(
    operation_id="GET /vacancies",
    name="search_vacancies",
    summary="Search hh.ru vacancies",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=VacancySearchParams,
    docstring_en=(
        "Search vacancies on hh.ru. Frequent filters (text, area, salary, "
        "currency, experience, employment, schedule, search_field, page, "
        "per_page, order_by and others) are top-level parameters."
        + _ADVANCED_NOTE
        + " Resolve ids first: dict_areas, dict_professional_roles, "
        "dict_industries, dict_metro. The response includes found, pages "
        "and clusters for pagination."
    ),
)

GET_VACANCY = make_tool(
    operation_id="GET /vacancies/{vacancy_id}",
    name="get_vacancy",
    summary="Get a single vacancy by id",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=VacancyIdParams,
    docstring_en=(
        "Get full details of one vacancy by its numeric id, including "
        "salary, key skills, contacts and branded description."
    ),
)

SIMILAR_VACANCIES = make_tool(
    operation_id="GET /vacancies/{vacancy_id}/similar_vacancies",
    name="similar_vacancies",
    summary="Get vacancies similar to the given one",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=SimilarVacanciesParams,
    docstring_en=(
        "Get vacancies similar to the given vacancy id; supports the same "
        "frequent filters as search_vacancies plus the nested advanced "
        "object for rare filters."
    ),
)

RELATED_VACANCIES = make_tool(
    operation_id="GET /vacancies/{vacancy_id}/related_vacancies",
    name="related_vacancies",
    summary="Get vacancies of the same employer",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=SimilarVacanciesParams,
    docstring_en=(
        "Get other vacancies of the employer that published the given "
        "vacancy; supports frequent filters plus the nested advanced "
        "object for rare filters."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    SEARCH_VACANCIES,
    GET_VACANCY,
    SIMILAR_VACANCIES,
    RELATED_VACANCIES,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
