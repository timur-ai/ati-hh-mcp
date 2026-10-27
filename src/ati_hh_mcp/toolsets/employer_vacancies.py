"""Набор «employer_vacancies»: управление вакансиями работодателя – 23 операции.

Все инструменты требуют токен работодателя hh.ru (``requires_auth=True``);
мутации (POST/PUT/DELETE) выполняются только после явного ``confirm=True``.

Тела операций создания/редактирования (объект вакансии по схеме
VacancyCreate/VacancyDraft, шаблон письма, сортировка откликов)
передаются параметром ``body`` – свободным словарём; query-параметры
мутаций hh.ru (``ignore_duplicates``, ``publication_period`` и др.)
уходят в query-строку через ``query_fields``. Операции с пустым телом
в спеке (архивация, скрытие, публикация черновика) тело не отправляют.
Операции, у которых вендор-спека декларирует form-тело
(``PUT /vacancies/{id}/preferred_negotiations_order``), отправляются
``application/x-www-form-urlencoded`` через ``body_format="form"``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "employer_vacancies"

_BODY_VACANCY = (
    "Vacancy object per hh.ru VacancyCreate schema, e.g. "
    '{"name": "...", "area": {"id": "113"}, "type": {"id": "open"}, '
    '"salary": {"from": 100000, "to": 150000, "currency": "RUR"}, '
    '"employer": {"id": "..."}, "professional_roles": [...]}: full field '
    "list in the hh.ru API docs."
)
_BODY_DRAFT = (
    "Draft fields per hh.ru VacancyDraftVacancyDraftCreate schema "
    "(same shape as the vacancy object of employer_create_vacancy)."
)


class CreateVacancyParams(BaseModel):
    """POST /vacancies: публикация вакансии."""

    body: dict[str, Any] = Field(..., description=_BODY_VACANCY)
    ignore_duplicates: bool | None = Field(
        None, description="Publish even if a duplicate active vacancy exists."
    )


class UpdateVacancyParams(BaseModel):
    """PUT /vacancies/{vacancy_id}: редактирование вакансии."""

    vacancy_id: str = Field(..., description="Vacancy id to edit.")
    body: dict[str, Any] = Field(..., description=_BODY_VACANCY)
    ignore_duplicates: bool | None = Field(
        None, description="Save even if a duplicate active vacancy exists."
    )
    ignore_replacement_warning: bool | None = Field(
        None, description="Skip the auto-replacement warning (vacancies of the same employer)."
    )


class ProlongateInfoParams(BaseModel):
    """GET /vacancies/{vacancy_id}/prolongate: возможность продления."""

    vacancy_id: str = Field(..., description="Vacancy id.")
    publication_period: int | None = Field(
        None, description="Publication period in days to check prolongation for."
    )


class ProlongateVacancyParams(BaseModel):
    """POST /vacancies/{vacancy_id}/prolongate: продление вакансии."""

    vacancy_id: str = Field(..., description="Vacancy id to prolong.")
    publication_period: int | None = Field(
        None, description="Publication period in days (30 by default)."
    )


class ActiveVacanciesParams(BaseModel):
    """GET /employers/{employer_id}/vacancies/active: опубликованные."""

    employer_id: str = Field(..., description="Employer id.")
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 100).")
    manager_id: str | None = Field(None, description="Filter by manager id.")
    manager_ids: str | None = Field(
        None, description="Filter by multiple manager ids (comma-separated)."
    )
    text: str | None = Field(None, description="Filter vacancies by free text.")
    area: str | None = Field(
        None, description="Filter by region id or ids (comma-separated)."
    )
    all_accessible: bool | None = Field(
        None, description="Include vacancies accessible to the current manager."
    )
    department_id: str | None = Field(None, description="Filter by department id.")
    resume_id: str | None = Field(
        None, description="Only vacancies matching this resume (relevant search)."
    )
    order_by: str | None = Field(
        None, description="Result order, e.g. publication_time or expiration_time."
    )


class EmployerVacancyListParams(BaseModel):
    """GET archived/hidden списки вакансий работодателя."""

    employer_id: str = Field(..., description="Employer id.")
    manager_id: str | None = Field(None, description="Filter by manager id.")
    order_by: str | None = Field(None, description="Result order.")
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page.")


class EmployerVacancyActionParams(BaseModel):
    """PUT/DELETE операций над вакансией работодателя (архив/скрытие)."""

    employer_id: str = Field(..., description="Employer id.")
    vacancy_id: str = Field(..., description="Vacancy id.")


class DraftListParams(BaseModel):
    """GET /vacancies/drafts: список черновиков."""

    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page.")


class DraftIdParams(BaseModel):
    """GET/DELETE /vacancies/drafts/{draft_id}."""

    draft_id: str = Field(..., description="Vacancy draft id.")


class CreateDraftParams(BaseModel):
    """POST /vacancies/drafts: создание черновика."""

    body: dict[str, Any] = Field(..., description=_BODY_DRAFT)


class UpdateDraftParams(BaseModel):
    """PUT /vacancies/drafts/{draft_id}: изменение черновика."""

    draft_id: str = Field(..., description="Vacancy draft id.")
    body: dict[str, Any] = Field(..., description=_BODY_DRAFT)


class DeleteAutoPublicationParams(BaseModel):
    """DELETE /vacancies/auto_publication: отмена автопубликации."""

    draft_id: str = Field(..., description="Draft id whose scheduled publication to cancel.")


class PreferredOrderGetParams(BaseModel):
    """GET /vacancies/{id}/preferred_negotiations_order."""

    id: str = Field(..., description="Vacancy id.")


class PreferredOrderSetParams(BaseModel):
    """PUT /vacancies/{id}/preferred_negotiations_order."""

    id: str = Field(..., description="Vacancy id.")
    body: dict[str, Any] = Field(
        ...,
        description=(
            'Preferred order, e.g. {"order": "last_change_time"}; order ids '
            "come from the order_types field of employer negotiations "
            "(get_negotiations response)."
        ),
    )


class VacancyIdOnlyParams(BaseModel):
    """GET stats/upgrades: только идентификатор вакансии."""

    vacancy_id: str = Field(..., description="Vacancy id.")


class VisitorsParams(BaseModel):
    """GET /vacancies/{vacancy_id}/visitors: посмотревшие вакансию."""

    vacancy_id: str = Field(..., description="Vacancy id.")
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page.")


EMPLOYER_CREATE_VACANCY = make_tool(
    operation_id="POST /vacancies",
    name="employer_create_vacancy",
    summary="Publish a new vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=CreateVacancyParams,
    query_fields={"ignore_duplicates"},
    docstring_en=(
        "Publish a new vacancy on behalf of the employer. The vacancy "
        "object goes into the `body` parameter. Mutation: requires "
        "confirm=True."
    ),
)

EMPLOYER_UPDATE_VACANCY = make_tool(
    operation_id="PUT /vacancies/{vacancy_id}",
    name="employer_update_vacancy",
    summary="Edit a published vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=UpdateVacancyParams,
    query_fields={"ignore_duplicates", "ignore_replacement_warning"},
    docstring_en=(
        "Edit a published vacancy: the full edited vacancy object goes "
        "into `body`. Mutation: requires confirm=True."
    ),
)

EMPLOYER_GET_PROLONGATE_INFO = make_tool(
    operation_id="GET /vacancies/{vacancy_id}/prolongate",
    name="employer_get_prolongate_info",
    summary="Check vacancy prolongation options",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ProlongateInfoParams,
    docstring_en=(
        "Get information about prolonging a vacancy: possible terms and "
        "their cost before actually prolonging."
    ),
)

EMPLOYER_PROLONGATE_VACANCY = make_tool(
    operation_id="POST /vacancies/{vacancy_id}/prolongate",
    name="employer_prolongate_vacancy",
    summary="Prolong a published vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=ProlongateVacancyParams,
    query_fields={"publication_period"},
    docstring_en=(
        "Prolong a published vacancy by publication_period days. Mutation: "
        "requires confirm=True."
    ),
)

EMPLOYER_LIST_ACTIVE_VACANCIES = make_tool(
    operation_id="GET /employers/{employer_id}/vacancies/active",
    name="employer_list_active_vacancies",
    summary="List published vacancies of an employer",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ActiveVacanciesParams,
    docstring_en=(
        "List active (published) vacancies of the employer with filters "
        "by manager, region, text and pagination."
    ),
)

EMPLOYER_LIST_ARCHIVED_VACANCIES = make_tool(
    operation_id="GET /employers/{employer_id}/vacancies/archived",
    name="employer_list_archived_vacancies",
    summary="List archived vacancies of an employer",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerVacancyListParams,
    docstring_en=(
        "List archived vacancies of the employer with manager filter, "
        "ordering and pagination."
    ),
)

EMPLOYER_ARCHIVE_VACANCY = make_tool(
    operation_id="PUT /employers/{employer_id}/vacancies/archived/{vacancy_id}",
    name="employer_archive_vacancy",
    summary="Archive a vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=EmployerVacancyActionParams,
    docstring_en=(
        "Move a published vacancy to the archive. Mutation: requires "
        "confirm=True."
    ),
)

EMPLOYER_LIST_HIDDEN_VACANCIES = make_tool(
    operation_id="GET /employers/{employer_id}/vacancies/hidden",
    name="employer_list_hidden_vacancies",
    summary="List hidden (deleted) vacancies of an employer",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerVacancyListParams,
    docstring_en=(
        "List hidden (deleted) vacancies of the employer; they can be "
        "restored with employer_unhide_vacancy."
    ),
)

EMPLOYER_HIDE_VACANCY = make_tool(
    operation_id="PUT /employers/{employer_id}/vacancies/hidden/{vacancy_id}",
    name="employer_hide_vacancy",
    summary="Hide (delete) a vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=EmployerVacancyActionParams,
    docstring_en=(
        "Hide (soft-delete) a vacancy: it leaves the search but can be "
        "restored. Mutation: requires confirm=True."
    ),
)

EMPLOYER_UNHIDE_VACANCY = make_tool(
    operation_id="DELETE /employers/{employer_id}/vacancies/hidden/{vacancy_id}",
    name="employer_unhide_vacancy",
    summary="Restore a hidden vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=EmployerVacancyActionParams,
    docstring_en=(
        "Restore a previously hidden vacancy from the deleted list. "
        "Mutation: requires confirm=True."
    ),
)

EMPLOYER_LIST_VACANCY_DRAFTS = make_tool(
    operation_id="GET /vacancies/drafts",
    name="employer_list_vacancy_drafts",
    summary="List vacancy drafts",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=DraftListParams,
    docstring_en="List vacancy drafts of the current employer with pagination.",
)

EMPLOYER_CREATE_VACANCY_DRAFT = make_tool(
    operation_id="POST /vacancies/drafts",
    name="employer_create_vacancy_draft",
    summary="Create a vacancy draft",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=CreateDraftParams,
    docstring_en=(
        "Create a vacancy draft (published later with "
        "employer_publish_vacancy_draft). Mutation: requires confirm=True."
    ),
)

EMPLOYER_GET_VACANCY_DRAFT = make_tool(
    operation_id="GET /vacancies/drafts/{draft_id}",
    name="employer_get_vacancy_draft",
    summary="Get a vacancy draft by id",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=DraftIdParams,
    docstring_en="Get one vacancy draft by its id.",
)

EMPLOYER_UPDATE_VACANCY_DRAFT = make_tool(
    operation_id="PUT /vacancies/drafts/{draft_id}",
    name="employer_update_vacancy_draft",
    summary="Edit a vacancy draft",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=UpdateDraftParams,
    docstring_en=(
        "Edit a vacancy draft: the edited draft fields go into `body`. "
        "Mutation: requires confirm=True."
    ),
)

EMPLOYER_DELETE_VACANCY_DRAFT = make_tool(
    operation_id="DELETE /vacancies/drafts/{draft_id}",
    name="employer_delete_vacancy_draft",
    summary="Delete a vacancy draft",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=DraftIdParams,
    docstring_en="Delete a vacancy draft. Mutation: requires confirm=True.",
)

EMPLOYER_PUBLISH_VACANCY_DRAFT = make_tool(
    operation_id="POST /vacancies/drafts/{draft_id}/publish",
    name="employer_publish_vacancy_draft",
    summary="Publish a vacancy from a draft",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=DraftIdParams,
    docstring_en=(
        "Publish the vacancy stored in the draft. Mutation: requires "
        "confirm=True."
    ),
)

EMPLOYER_LIST_DRAFT_DUPLICATES = make_tool(
    operation_id="GET /vacancies/drafts/{draft_id}/duplicates",
    name="employer_list_draft_duplicates",
    summary="Check a draft for duplicate vacancies",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=DraftIdParams,
    docstring_en=(
        "Check the draft for duplicates among active vacancies of the "
        "employer before publishing."
    ),
)

EMPLOYER_DELETE_AUTO_PUBLICATION = make_tool(
    operation_id="DELETE /vacancies/auto_publication",
    name="employer_delete_auto_publication",
    summary="Cancel scheduled draft auto-publication",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=DeleteAutoPublicationParams,
    docstring_en=(
        "Cancel the scheduled automatic publication of a draft. Mutation: "
        "requires confirm=True."
    ),
)

EMPLOYER_GET_PREFERRED_NEGOTIATIONS_ORDER = make_tool(
    operation_id="GET /vacancies/{id}/preferred_negotiations_order",
    name="employer_get_preferred_negotiations_order",
    summary="Get preferred negotiations order of a vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=PreferredOrderGetParams,
    docstring_en=(
        "Get the preferred sorting order of responses (negotiations) for "
        "the vacancy."
    ),
)

EMPLOYER_SET_PREFERRED_NEGOTIATIONS_ORDER = make_tool(
    operation_id="PUT /vacancies/{id}/preferred_negotiations_order",
    name="employer_set_preferred_negotiations_order",
    summary="Set preferred negotiations order of a vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=PreferredOrderSetParams,
    body_format="form",
    docstring_en=(
        'Set the preferred sorting order of responses for the vacancy: '
        'body like {"order": "last_change_time"} (sent form-encoded). '
        "Mutation: requires confirm=True."
    ),
)

EMPLOYER_GET_VACANCY_STATS = make_tool(
    operation_id="GET /vacancies/{vacancy_id}/stats",
    name="employer_get_vacancy_stats",
    summary="Get vacancy statistics",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=VacancyIdOnlyParams,
    docstring_en=(
        "Get statistics of a published vacancy: views, responses and "
        "other counters."
    ),
)

EMPLOYER_GET_VACANCY_VISITORS = make_tool(
    operation_id="GET /vacancies/{vacancy_id}/visitors",
    name="employer_get_vacancy_visitors",
    summary="Get vacancy visitors",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=VisitorsParams,
    docstring_en=(
        "Get candidates who viewed the vacancy, with pagination."
    ),
)

EMPLOYER_GET_VACANCY_UPGRADES = make_tool(
    operation_id="GET /vacancies/{vacancy_id}/upgrades",
    name="employer_get_vacancy_upgrades",
    summary="List available upgrades for a vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=VacancyIdOnlyParams,
    docstring_en=(
        "List paid upgrades (promotion options) available for the vacancy."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    EMPLOYER_CREATE_VACANCY,
    EMPLOYER_UPDATE_VACANCY,
    EMPLOYER_GET_PROLONGATE_INFO,
    EMPLOYER_PROLONGATE_VACANCY,
    EMPLOYER_LIST_ACTIVE_VACANCIES,
    EMPLOYER_LIST_ARCHIVED_VACANCIES,
    EMPLOYER_ARCHIVE_VACANCY,
    EMPLOYER_LIST_HIDDEN_VACANCIES,
    EMPLOYER_HIDE_VACANCY,
    EMPLOYER_UNHIDE_VACANCY,
    EMPLOYER_LIST_VACANCY_DRAFTS,
    EMPLOYER_CREATE_VACANCY_DRAFT,
    EMPLOYER_GET_VACANCY_DRAFT,
    EMPLOYER_UPDATE_VACANCY_DRAFT,
    EMPLOYER_DELETE_VACANCY_DRAFT,
    EMPLOYER_PUBLISH_VACANCY_DRAFT,
    EMPLOYER_LIST_DRAFT_DUPLICATES,
    EMPLOYER_DELETE_AUTO_PUBLICATION,
    EMPLOYER_GET_PREFERRED_NEGOTIATIONS_ORDER,
    EMPLOYER_SET_PREFERRED_NEGOTIATIONS_ORDER,
    EMPLOYER_GET_VACANCY_STATS,
    EMPLOYER_GET_VACANCY_VISITORS,
    EMPLOYER_GET_VACANCY_UPGRADES,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
