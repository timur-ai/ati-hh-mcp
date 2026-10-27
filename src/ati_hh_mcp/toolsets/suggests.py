"""Набор «suggests»: подсказки (автодополнение) hh.ru – 11 операций.

Подсказки возвращают короткие списки подходящих значений по началу
строки; используются для поиска идентификаторов (регионов, навыков,
компаний) перед основным запросом.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "suggests"


class TextParams(BaseModel):
    """Базовая модель подсказок: обязательный текст запроса."""

    text: str


class AreaLeavesParams(BaseModel):
    """GET /suggests/area_leaves: листовые регионы внутри региона."""

    text: str
    area_id: str | None = None


class AreasSuggestParams(BaseModel):
    """GET /suggests/areas: регионы по началу названия."""

    text: str
    area_id: str | None = None
    include_parent: bool | None = None


SUGGEST_AREAS = make_tool(
    operation_id="GET /suggests/areas",
    name="suggest_areas",
    summary="Suggest regions by name prefix",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=AreasSuggestParams,
    docstring_en=(
        "Suggest hh.ru regions (areas) by name prefix; returns matching "
        "areas with ids. area_id narrows the search to children of a given "
        "region, include_parent=true adds the parent region to the response."
    ),
)

SUGGEST_AREA_LEAVES = make_tool(
    operation_id="GET /suggests/area_leaves",
    name="suggest_area_leaves",
    summary="Suggest leaf regions inside a region",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=AreaLeavesParams,
    docstring_en=(
        "Suggest leaf regions (cities/districts without children) inside "
        "area_id by name prefix; used to pick concrete locations."
    ),
)

SUGGEST_COMPANIES = make_tool(
    operation_id="GET /suggests/companies",
    name="suggest_companies",
    summary="Suggest employers by name prefix",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=TextParams,
    docstring_en=(
        "Suggest registered employers (companies) by name prefix with "
        "their ids and urls."
    ),
)

SUGGEST_EDUCATIONAL_INSTITUTIONS = make_tool(
    operation_id="GET /suggests/educational_institutions",
    name="suggest_educational_institutions",
    summary="Suggest educational institutions by name prefix",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=TextParams,
    docstring_en=(
        "Suggest educational institutions by name prefix with their ids."
    ),
)

SUGGEST_FIELDS_OF_STUDY = make_tool(
    operation_id="GET /suggests/fields_of_study",
    name="suggest_fields_of_study",
    summary="Suggest fields of study by name prefix",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=TextParams,
    docstring_en=(
        "Suggest fields of study (specialties) by name prefix with their "
        "ids for resume and vacancy education blocks."
    ),
)

SUGGEST_POSITIONS = make_tool(
    operation_id="GET /suggests/positions",
    name="suggest_positions",
    summary="Suggest positions for a resume",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=TextParams,
    docstring_en=(
        "Suggest job positions (titles) by name prefix for resumes; "
        "returns positions with professional role ids."
    ),
)

SUGGEST_PROFESSIONAL_ROLES = make_tool(
    operation_id="GET /suggests/professional_roles",
    name="suggest_professional_roles",
    summary="Suggest professional roles by name prefix",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=TextParams,
    docstring_en=(
        "Suggest professional roles by name prefix with their ids for "
        "vacancy and resume search."
    ),
)

SUGGEST_RESUME_SEARCH_KEYWORD = make_tool(
    operation_id="GET /suggests/resume_search_keyword",
    name="suggest_resume_search_keyword",
    summary="Suggest resume search keywords",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=TextParams,
    docstring_en=(
        "Suggest full search phrases for resume search by a partial "
        "keyword (employer side)."
    ),
)

SUGGEST_SKILL_SET = make_tool(
    operation_id="GET /suggests/skill_set",
    name="suggest_skill_set",
    summary="Suggest key skills by name prefix",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=TextParams,
    docstring_en=(
        "Suggest key skills by name prefix with their ids; skill ids are "
        "accepted by dict_skills."
    ),
)

SUGGEST_VACANCY_POSITIONS = make_tool(
    operation_id="GET /suggests/vacancy_positions",
    name="suggest_vacancy_positions",
    summary="Suggest positions for a vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=TextParams,
    docstring_en=(
        "Suggest job positions (titles) by name prefix for vacancies; "
        "returns positions with professional role ids."
    ),
)

SUGGEST_VACANCY_SEARCH_KEYWORD = make_tool(
    operation_id="GET /suggests/vacancy_search_keyword",
    name="suggest_vacancy_search_keyword",
    summary="Suggest vacancy search keywords",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=TextParams,
    docstring_en=(
        "Suggest full search phrases for vacancy search by a partial "
        "keyword (applicant side)."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    SUGGEST_AREAS,
    SUGGEST_AREA_LEAVES,
    SUGGEST_COMPANIES,
    SUGGEST_EDUCATIONAL_INSTITUTIONS,
    SUGGEST_FIELDS_OF_STUDY,
    SUGGEST_POSITIONS,
    SUGGEST_PROFESSIONAL_ROLES,
    SUGGEST_RESUME_SEARCH_KEYWORD,
    SUGGEST_SKILL_SET,
    SUGGEST_VACANCY_POSITIONS,
    SUGGEST_VACANCY_SEARCH_KEYWORD,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
