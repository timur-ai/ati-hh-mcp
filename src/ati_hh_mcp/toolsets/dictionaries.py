"""Набор «dictionaries»: справочники hh.ru (16 операций).

Инструменты соответствуют операциям публичной OpenAPI один-к-одному;
соответствие (включая параметры) проверяется контрактным метатестом
``tests/contract/test_coverage.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "dictionaries"


class AreaParams(BaseModel):
    """GET /areas: дерево регионов целиком."""

    additional_case: str | None = None


class AreaByIdParams(BaseModel):
    """GET /areas/{area_id}: один регион по идентификатору."""

    area_id: str
    additional_case: str | None = None


class MetroCityParams(BaseModel):
    """GET /metro/{city_id}: метро конкретного города."""

    city_id: str


class SkillsParams(BaseModel):
    """GET /skills: ключевые навыки по идентификаторам."""

    id: str


class EducationalInstitutionsParams(BaseModel):
    """GET /educational_institutions: учебные заведения по идентификаторам."""

    id: str


class FacultiesParams(BaseModel):
    """GET /educational_institutions/{id}/faculties: факультеты заведения."""

    id: str


DICT_DICTIONARIES = make_tool(
    operation_id="GET /dictionaries",
    name="dict_dictionaries",
    summary="Get hh.ru core dictionaries",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get hh.ru core dictionaries: currencies, genders, vacancies statuses "
        "and other enumerations used across the API."
    ),
)

DICT_AREAS = make_tool(
    operation_id="GET /areas",
    name="dict_areas",
    summary="Get the hh.ru regions tree",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=AreaParams,
    docstring_en=(
        "Get the full tree of hh.ru regions (areas): countries, federal "
        "subjects and cities, with their numeric ids. Optional "
        "additional_case=prepositional adds a Russian prepositional-case name."
    ),
)

DICT_AREA_COUNTRIES = make_tool(
    operation_id="GET /areas/countries",
    name="dict_area_countries",
    summary="Get the list of countries",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get the list of countries known to hh.ru with their numeric ids "
        "(each country is also an area)."
    ),
)

DICT_AREA = make_tool(
    operation_id="GET /areas/{area_id}",
    name="dict_area",
    summary="Get a single region by id",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=AreaByIdParams,
    docstring_en=(
        "Get one hh.ru region (area) by its numeric id, including nested "
        "children. Optional additional_case=prepositional adds a Russian "
        "prepositional-case name."
    ),
)

DICT_INDUSTRIES = make_tool(
    operation_id="GET /industries",
    name="dict_industries",
    summary="Get the industries tree",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get the tree of industries (spheres of company activity) with "
        "sub-industries and their ids."
    ),
)

DICT_PROFESSIONAL_ROLES = make_tool(
    operation_id="GET /professional_roles",
    name="dict_professional_roles",
    summary="Get the professional roles tree",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get the tree of professional roles (job categories) with "
        "sub-categories and their numeric ids; role ids are used in vacancy "
        "and resume search."
    ),
)

DICT_LANGUAGES = make_tool(
    operation_id="GET /languages",
    name="dict_languages",
    summary="Get the languages dictionary",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en="Get the dictionary of foreign languages with their ids.",
)

DICT_LOCALES = make_tool(
    operation_id="GET /locales",
    name="dict_locales",
    summary="Get the supported locales",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en="Get the locales supported by hh.ru (vacancy interface).",
)

DICT_RESUME_LOCALES = make_tool(
    operation_id="GET /locales/resume",
    name="dict_resume_locales",
    summary="Get the locales supported in resumes",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en="Get the locales supported in hh.ru resumes.",
)

DICT_DISTRICTS = make_tool(
    operation_id="GET /districts",
    name="dict_districts",
    summary="Get the districts of Russian cities",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get the administrative districts of Russian cities (district ids "
        "narrow down a vacancy search within a city)."
    ),
)

DICT_METRO = make_tool(
    operation_id="GET /metro",
    name="dict_metro",
    summary="Get hh.ru metro lines and stations",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get metro lines and stations for all hh.ru cities that have a metro "
        "map, grouped by city with station ids."
    ),
)

DICT_METRO_CITY = make_tool(
    operation_id="GET /metro/{city_id}",
    name="dict_metro_city",
    summary="Get metro stations of one city",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=MetroCityParams,
    docstring_en=(
        "Get metro lines and stations of a single city by area id "
        "(for example 4 = Moscow)."
    ),
)

DICT_SKILLS = make_tool(
    operation_id="GET /skills",
    name="dict_skills",
    summary="Get key skills by ids",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=SkillsParams,
    docstring_en=(
        "Get key skills by id (one or several; up to 50 values per request). "
        "Find skill ids with suggest_skill_set."
    ),
)

DICT_EDUCATIONAL_INSTITUTIONS = make_tool(
    operation_id="GET /educational_institutions",
    name="dict_educational_institutions",
    summary="Get educational institutions by ids",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=EducationalInstitutionsParams,
    docstring_en=(
        "Get educational institutions by id (up to 50 values per request). "
        "Find institution ids with suggest_educational_institutions."
    ),
)

DICT_FACULTIES = make_tool(
    operation_id="GET /educational_institutions/{id}/faculties",
    name="dict_faculties",
    summary="Get faculties of an educational institution",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=FacultiesParams,
    docstring_en=(
        "Get the faculty list of one educational institution by its id."
    ),
)

DICT_VACANCY_CONDITIONS = make_tool(
    operation_id="GET /vacancy_conditions",
    name="dict_vacancy_conditions",
    summary="Get the vacancy placement conditions",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get the dictionary of paid vacancy placement conditions (branded "
        "templates, priority placement and similar options)."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    DICT_DICTIONARIES,
    DICT_AREAS,
    DICT_AREA_COUNTRIES,
    DICT_AREA,
    DICT_INDUSTRIES,
    DICT_PROFESSIONAL_ROLES,
    DICT_LANGUAGES,
    DICT_LOCALES,
    DICT_RESUME_LOCALES,
    DICT_DISTRICTS,
    DICT_METRO,
    DICT_METRO_CITY,
    DICT_SKILLS,
    DICT_EDUCATIONAL_INSTITUTIONS,
    DICT_FACULTIES,
    DICT_VACANCY_CONDITIONS,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу.

    ``client_factory`` задаёт фабрику HHClient для инструментов набора
    (контракт волны 2); без аргумента остаётся текущая глобальная.
    """
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
