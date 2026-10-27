"""Набор «employer_misc»: прочие операции работодателя и публичные справочники – 25 операций.

Состав (план M3d): поиск/просмотр работодателей (публичные), адреса,
департаменты, услуги (платные методы, варианты публикации), тесты,
бренд-шаблоны и регионы вакансий, звонки (история, ссылка, POST-поиски
записей и транскриптов), статистика Clickme, webhook-подписки,
зарплатная статистика (4 публичных справочника + платная оценка) и
шаблоны сообщений для откликов.

Исключение из правила «не-GET = мутация»: ``POST /calls/records/search``
и ``POST /calls/transcripts/search`` семантически являются поиском
(чтение) – реализованы с ``is_mutation=False`` без ``confirm``; их тела
передаются свободным JSON-объектом ``body`` (как и у webhook-мутаций),
поскольку параметрический контракт метатеста сверяет только query/path
параметры операций.

Публичные операции без токена hh.ru (``requires_auth=False``): поиск и
просмотр работодателей, четыре справочника зарплатной статистики.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "employer_misc"


class EmployerSearchParams(BaseModel):
    """GET /employers: публичный поиск работодателей."""

    text: str | None = Field(
        None, description="Search text matched against employer name and description."
    )
    area: str | None = Field(
        None, description="Region id or ids (comma-separated) from dict_areas."
    )
    type: str | None = Field(
        None, description="Employer type id(s) (employer_type field of get_dictionaries)."
    )
    only_with_vacancies: bool | None = Field(
        None, description="Only employers with currently open vacancies (default false)."
    )
    sort_by: str | None = Field(
        None, description="Sort order: by_name (default) or by_vacancies_open."
    )
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 100, default 20).")


class EmployerIdParams(BaseModel):
    """GET /employers/{employer_id}: карточка работодателя (публичная)."""

    employer_id: str = Field(..., description="Employer id (from search_employers).")


class EmployerAddressesParams(BaseModel):
    """GET /employers/{employer_id}/addresses: список адресов."""

    employer_id: str = Field(..., description="Employer id.")
    changed_after: str | None = Field(
        None,
        description="Load only addresses changed after this datetime (ISO 8601 with "
        "timezone, max 7 days back); adds a deleted flag per address, "
        "pagination is ignored.",
    )
    manager_id: str | None = Field(None, description="Filter addresses by creating manager id.")
    with_manager: bool | None = Field(
        None, description="Include info about the manager who created each address."
    )
    per_page: int | None = Field(None, description="Items per page (max 10000).")
    page: int | None = Field(None, description="Page number, zero-based.")


class EmployerAddressItemParams(BaseModel):
    """GET /employers/{employer_id}/addresses/{address_id}: один адрес."""

    employer_id: str = Field(..., description="Employer id.")
    address_id: str = Field(..., description="Employer address id.")
    with_manager: bool | None = Field(
        None, description="Include info about the manager who created the address."
    )


class AvailablePublicationsParams(BaseModel):
    """GET .../services/available_publications: варианты публикации вакансии."""

    employer_id: str = Field(..., description="Employer id.")
    area_id: str | None = Field(None, description="Region id to get publication options for.")
    professional_role_id: str | None = Field(
        None, description="Professional role id to get publication options for."
    )


class CallsHistoryParams(BaseModel):
    """GET /calls/history: пагинированная история звонков (курсоры)."""

    vacancy_id: list[str] | None = Field(
        None, description="Vacancy id(s) to filter calls by (repeatable list)."
    )
    date_from: str | None = Field(
        None, description="Range start, ISO 8601 with offset (e.g. 2026-07-01T00:00:00+00:00)."
    )
    date_to: str | None = Field(None, description="Range end, ISO 8601 with offset.")
    per_page: int | None = Field(None, description="Page size (1..500).")
    next_cursor: str | None = Field(
        None, description="Cursor of the next page taken from a previous response."
    )
    previous_cursor: str | None = Field(
        None, description="Cursor of the previous page taken from a previous response."
    )
    successful: bool | None = Field(None, description="Filter by call success.")
    direction: str | None = Field(
        None, description="Call direction: outgoing (manager calls) or incoming."
    )
    with_resume: bool | None = Field(
        None, description="true – only calls with a resume, false – only without."
    )
    without_vacancy: bool | None = Field(
        None, description="true – only calls not tied to a vacancy."
    )
    link_id: str | None = Field(
        None, description="Link id from employer_get_call_link: only calls made via it."
    )
    with_records: bool | None = Field(
        None, description="Include each call's recording when available (default false)."
    )
    with_transcripts: bool | None = Field(
        None, description="Include each call's transcript when available (default false)."
    )


class CallLinkParams(BaseModel):
    """GET /calls/link: ссылка/QR для звонка соискателю."""

    resume_id: str = Field(..., description="Resume id of the applicant to call.")
    vacancy_id: str | None = Field(
        None,
        description="Vacancy id for access check; required for hiring managers, "
        "positive integer as string.",
    )


class CallSearchBodyParams(BaseModel):
    """POST /calls/{records|transcripts}/search: тело поиска (чтение, без confirm)."""

    body: dict[str, Any] = Field(
        ...,
        description='Search object: exactly one of {"call_ids": [str]} (max 250, from '
        'employer_get_call_history) or {"link_ids": [uuid]} (max 50, from '
        "employer_get_call_link) must be filled.",
    )


class ClickmeStatisticsParams(BaseModel):
    """GET /clickme/statistics: статистика рекламных кампаний."""

    date_from: str = Field(..., description="Statistics start date (YYYY-MM-DD).")
    date_to: str = Field(..., description="Statistics end date, inclusive (YYYY-MM-DD).")
    with_banners: bool | None = Field(
        None, description="Additionally aggregate statistics per banner."
    )


class WebhookSubscriptionCreateParams(BaseModel):
    """POST /webhook/subscriptions: подписка на события."""

    body: dict[str, Any] = Field(
        ...,
        description='Subscription object {"url": str, "actions": [{"type": str}]}: one url '
        "per application; action types are listed in the hh.ru webhook docs "
        "(e.g. VACANCY_CHANGE, CHAT_MESSAGE_CREATED, NEW_NEGOTIATION_VACANCY).",
    )


class WebhookSubscriptionUpdateParams(BaseModel):
    """PUT /webhook/subscriptions/{subscription_id}: изменение подписки."""

    subscription_id: str = Field(..., description="Subscription id.")
    body: dict[str, Any] = Field(
        ...,
        description='Fields to update, e.g. {"url": str} or {"actions": [{"type": str}]}: '
        "actions replaces the whole list and cannot be empty.",
    )


class WebhookSubscriptionIdParams(BaseModel):
    """DELETE /webhook/subscriptions/{subscription_id}: удаление подписки."""

    subscription_id: str = Field(..., description="Subscription id to cancel.")


class SalaryEvaluationParams(BaseModel):
    """GET /salary_statistics/paid/salary_evaluation/{area_id}: оценка зарплаты."""

    area_id: str = Field(..., description="Region code (from dict_salary_areas).")
    exclude_area: str | None = Field(None, description="Region code(s) to exclude from the sample.")
    employee_level: str | None = Field(
        None, description="Competence level code(s) (from dict_salary_employee_levels)."
    )
    industry: str | None = Field(
        None, description="Industry code(s) for the sample (from dict_salary_industries)."
    )
    speciality: str | None = Field(
        None,
        description="Professional area/speciality code(s) (from dict_salary_professional_areas).",
    )
    extend_sources: bool | None = Field(
        None,
        description="Also use resume/vacancy salary data when the paid bank has "
        "insufficient data (default false).",
    )
    position_name: str | None = Field(
        None,
        description="Position name: the service derives speciality and level from it "
        "when those parameters are not passed.",
    )


class MessageTemplateParams(BaseModel):
    """GET /message_templates/{template}: шаблоны сообщений отклика/приглашения."""

    template: str = Field(
        ...,
        description="Template name: invite, invite_after_response, discard_after_response, "
        "discard_after_interview (the list may grow).",
    )
    topic_id: str | None = Field(
        None, description="Existing negotiation topic id; cannot be combined with the ids below."
    )
    vacancy_id: str | None = Field(
        None, description="Vacancy id; passed only together with resume_id."
    )
    resume_id: str | None = Field(
        None, description="Resume id; passed only together with vacancy_id."
    )


SEARCH_EMPLOYERS = make_tool(
    operation_id="GET /employers",
    name="search_employers",
    summary="Search employers",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=EmployerSearchParams,
    docstring_en=(
        "Search hh.ru employers by text, region or type (public, no token "
        "needed). Pagination depth is limited to 5000 results; sort by name "
        "or open-vacancy count."
    ),
)

GET_EMPLOYER = make_tool(
    operation_id="GET /employers/{employer_id}",
    name="get_employer",
    summary="Get employer info by id",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    param_model=EmployerIdParams,
    docstring_en=(
        "Get public employer information by id, including trusted status, "
        "site url and the vacancies URL."
    ),
)

EMPLOYER_LIST_ADDRESSES = make_tool(
    operation_id="GET /employers/{employer_id}/addresses",
    name="employer_list_addresses",
    summary="List employer addresses",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerAddressesParams,
    docstring_en=(
        "List employer addresses (paginated). changed_after returns all "
        "addresses changed since that moment (ISO 8601 with timezone, max 7 "
        "days back) with a deleted flag and without pagination; with_manager "
        "adds the creator info."
    ),
)

EMPLOYER_GET_ADDRESS = make_tool(
    operation_id="GET /employers/{employer_id}/addresses/{address_id}",
    name="employer_get_address",
    summary="Get one employer address",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerAddressItemParams,
    docstring_en="Get one employer address by id; with_manager adds the creator info.",
)

EMPLOYER_LIST_DEPARTMENTS = make_tool(
    operation_id="GET /employers/{employer_id}/departments",
    name="employer_list_departments",
    summary="List employer departments",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerIdParams,
    docstring_en=(
        "Department dictionary of the employer; values may change at any "
        "time – do not hard-code them."
    ),
)

EMPLOYER_LIST_PAYABLE_API_ACTIONS = make_tool(
    operation_id="GET /employers/{employer_id}/services/payable_api_actions/active",
    name="employer_list_payable_api_actions",
    summary="List active paid API services",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerIdParams,
    docstring_en=(
        "Active paid API services of the employer (each purchased service is "
        "a separate item; empty items when none are active). See "
        "employer_get_manager_method_access for the access groups."
    ),
)

EMPLOYER_LIST_AVAILABLE_PUBLICATIONS = make_tool(
    operation_id="GET /employers/{employer_id}/services/available_publications",
    name="employer_list_available_publications",
    summary="List available vacancy publication options",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=AvailablePublicationsParams,
    docstring_en=(
        "Vacancy publication options (packages) for the employer, optionally "
        "filtered by area_id and professional_role_id. Pass a suitable "
        "package's employer_service_id when publishing a vacancy to spend it."
    ),
)

EMPLOYER_LIST_TESTS = make_tool(
    operation_id="GET /employers/{employer_id}/tests",
    name="employer_list_tests",
    summary="List employer tests",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerIdParams,
    docstring_en="Tests saved by the employer.",
)

EMPLOYER_LIST_VACANCY_BRANDED_TEMPLATES = make_tool(
    operation_id="GET /employers/{employer_id}/vacancy_branded_templates",
    name="employer_list_vacancy_branded_templates",
    summary="List vacancy branded templates",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerIdParams,
    docstring_en=(
        "Branded vacancy templates available to the employer (requires the "
        "paid branding service; values may change at any time)."
    ),
)

EMPLOYER_LIST_ACTIVE_VACANCY_AREAS = make_tool(
    operation_id="GET /employers/{employer_id}/vacancy_areas/active",
    name="employer_list_active_vacancy_areas",
    summary="List regions with active vacancies of the employer",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerIdParams,
    docstring_en=(
        "Regions where the employer currently has active vacancies; values may change at any time."
    ),
)

EMPLOYER_GET_CALL_HISTORY = make_tool(
    operation_id="GET /calls/history",
    name="employer_get_call_history",
    summary="Get employer call history",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=CallsHistoryParams,
    docstring_en=(
        "Paginated (cursor-based) call history of the employer: site, app, "
        "QR, API-link and virtual-number calls. next_cursor/previous_cursor "
        "are mutually exclusive; their absence means the last/first page. "
        "with_records/with_transcripts embed media metadata into each call."
    ),
)

EMPLOYER_GET_CALL_LINK = make_tool(
    operation_id="GET /calls/link",
    name="employer_get_call_link",
    summary="Get a call link and QR code for an applicant",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=CallLinkParams,
    docstring_en=(
        "Time-limited call page link (expires_at) plus a Base64 SVG QR code "
        "for calling an applicant from hh.ru. The returned link_id is used "
        "in employer_get_call_history and the records/transcripts searches. "
        "vacancy_id is required for hiring managers."
    ),
)

EMPLOYER_SEARCH_CALL_RECORDS = make_tool(
    operation_id="POST /calls/records/search",
    name="employer_search_call_records",
    summary="Fetch call recordings by call or link ids",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=CallSearchBodyParams,
    docstring_en=(
        "Fetch recordings of finished calls (a search, no confirm needed). "
        'body: exactly one of {"call_ids": [...]} (max 250, from '
        'employer_get_call_history) or {"link_ids": [...]} (max 50, from '
        "employer_get_call_link). record_url values are temporary links."
    ),
)

EMPLOYER_SEARCH_CALL_TRANSCRIPTS = make_tool(
    operation_id="POST /calls/transcripts/search",
    name="employer_search_call_transcripts",
    summary="Fetch call transcripts by call or link ids",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=CallSearchBodyParams,
    docstring_en=(
        "Fetch transcripts of finished calls (a search, no confirm needed). "
        "body shape is the same as in employer_search_call_records; each "
        "transcript carries a status and, when SUCCESS, a temporary "
        "transcript_url with an expires_at moment."
    ),
)

EMPLOYER_GET_CLICKME_STATISTICS = make_tool(
    operation_id="GET /clickme/statistics",
    name="employer_get_clickme_statistics",
    summary="Get Clickme advertising campaign statistics",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ClickmeStatisticsParams,
    docstring_en=(
        "Statistics of Clickme advertising campaigns for a date range "
        "(inclusive); with_banners adds per-banner aggregation."
    ),
)

EMPLOYER_LIST_WEBHOOK_SUBSCRIPTIONS = make_tool(
    operation_id="GET /webhook/subscriptions",
    name="employer_list_webhook_subscriptions",
    summary="List webhook subscriptions",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    docstring_en=(
        "Webhook subscriptions of the current employer: each subscription "
        "has a url and a list of subscribed event types."
    ),
)

EMPLOYER_CREATE_WEBHOOK_SUBSCRIPTION = make_tool(
    operation_id="POST /webhook/subscriptions",
    name="employer_create_webhook_subscription",
    summary="Subscribe to webhook notifications",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=WebhookSubscriptionCreateParams,
    docstring_en=(
        'Create a webhook subscription: body {"url": str, "actions": '
        '[{"type": str}]}. One url per application for all events; hh.ru '
        "POSTs event objects to the url (2xx or 409 expected). Delivery is "
        "best-effort, not guaranteed. Returns 201."
    ),
)

EMPLOYER_UPDATE_WEBHOOK_SUBSCRIPTION = make_tool(
    operation_id="PUT /webhook/subscriptions/{subscription_id}",
    name="employer_update_webhook_subscription",
    summary="Update a webhook subscription",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=WebhookSubscriptionUpdateParams,
    docstring_en=(
        "Update url or actions of a subscription (send only the fields to "
        "change). actions replaces the whole list and cannot be empty. "
        "Returns 204."
    ),
)

EMPLOYER_DELETE_WEBHOOK_SUBSCRIPTION = make_tool(
    operation_id="DELETE /webhook/subscriptions/{subscription_id}",
    name="employer_delete_webhook_subscription",
    summary="Delete a webhook subscription",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=WebhookSubscriptionIdParams,
    docstring_en="Cancel a webhook subscription. Returns 204 on success.",
)

DICT_SALARY_INDUSTRIES = make_tool(
    operation_id="GET /salary_statistics/dictionaries/salary_industries",
    name="dict_salary_industries",
    summary="Salary statistics: industries dictionary",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Two-level dictionary of industries and activity spheres for the "
        "salary statistics bank (public, no token needed)."
    ),
)

DICT_SALARY_PROFESSIONAL_AREAS = make_tool(
    operation_id="GET /salary_statistics/dictionaries/professional_areas",
    name="dict_salary_professional_areas",
    summary="Salary statistics: professional areas dictionary",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Professional areas and specialities dictionary for the salary "
        "statistics bank (public, no token needed)."
    ),
)

DICT_SALARY_EMPLOYEE_LEVELS = make_tool(
    operation_id="GET /salary_statistics/dictionaries/employee_levels",
    name="dict_salary_employee_levels",
    summary="Salary statistics: competence levels dictionary",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Competence levels dictionary for the salary statistics bank (public, no token needed)."
    ),
)

DICT_SALARY_AREAS = make_tool(
    operation_id="GET /salary_statistics/dictionaries/salary_areas",
    name="dict_salary_areas",
    summary="Salary statistics: regions dictionary",
    toolset=TOOLSET_NAME,
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Regions, oblasts and cities dictionary for the salary statistics "
        "bank (public, no token needed)."
    ),
)

EMPLOYER_GET_SALARY_EVALUATION = make_tool(
    operation_id="GET /salary_statistics/paid/salary_evaluation/{area_id}",
    name="employer_get_salary_evaluation",
    summary="Evaluate a salary from the paid salary statistics bank",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=SalaryEvaluationParams,
    docstring_en=(
        "Salary statistics report without forecasting (paid access to the "
        "salary bank required). Codes come from the four dict_salary_* "
        "tools; position_name lets the service derive speciality and level "
        "on its own; extend_sources widens the sample with resume/vacancy "
        "data when the bank is insufficient."
    ),
)

GET_MESSAGE_TEMPLATE = make_tool(
    operation_id="GET /message_templates/{template}",
    name="get_message_template",
    summary="Get response message templates for a negotiation",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=MessageTemplateParams,
    docstring_en=(
        "Message templates for invitations and rejections (paid employer "
        "access). Pass either topic_id of an existing negotiation, or the "
        "vacancy_id + resume_id pair (never both). Template names: invite, "
        "invite_after_response, discard_after_response, discard_after_interview."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    SEARCH_EMPLOYERS,
    GET_EMPLOYER,
    EMPLOYER_LIST_ADDRESSES,
    EMPLOYER_GET_ADDRESS,
    EMPLOYER_LIST_DEPARTMENTS,
    EMPLOYER_LIST_PAYABLE_API_ACTIONS,
    EMPLOYER_LIST_AVAILABLE_PUBLICATIONS,
    EMPLOYER_LIST_TESTS,
    EMPLOYER_LIST_VACANCY_BRANDED_TEMPLATES,
    EMPLOYER_LIST_ACTIVE_VACANCY_AREAS,
    EMPLOYER_GET_CALL_HISTORY,
    EMPLOYER_GET_CALL_LINK,
    EMPLOYER_SEARCH_CALL_RECORDS,
    EMPLOYER_SEARCH_CALL_TRANSCRIPTS,
    EMPLOYER_GET_CLICKME_STATISTICS,
    EMPLOYER_LIST_WEBHOOK_SUBSCRIPTIONS,
    EMPLOYER_CREATE_WEBHOOK_SUBSCRIPTION,
    EMPLOYER_UPDATE_WEBHOOK_SUBSCRIPTION,
    EMPLOYER_DELETE_WEBHOOK_SUBSCRIPTION,
    DICT_SALARY_INDUSTRIES,
    DICT_SALARY_PROFESSIONAL_AREAS,
    DICT_SALARY_EMPLOYEE_LEVELS,
    DICT_SALARY_AREAS,
    EMPLOYER_GET_SALARY_EVALUATION,
    GET_MESSAGE_TEMPLATE,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
