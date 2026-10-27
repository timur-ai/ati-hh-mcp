"""Набор «employer_resumes»: поиск резюме, автопоиски, комментарии – 11 операций.

Тяжёлая операция ``GET /resumes`` (49 неслужебных query-параметров спеки,
~52 вместе со служебными ``Host``/``Locale``/``HHUserAgent``) реализована
двухуровневой схемой (решение реестра, план M3d, как у ``search_vacancies``):
обязательные и частые параметры – на верхнем уровне инструмента, длинный
хвост – во вложенной модели ``ResumeSearchAdvanced``; в HTTP-запрос
попадают только заданные поля.

Параметры спеки с точкой в имени (``text.logic``, ``text.field``,
``text.period``, ``text.company_size``) не бывают именами параметров
верхнего уровня (сигнатура инструмента требует валидный идентификатор
Python), поэтому они объявлены в ``ResumeSearchAdvanced`` с
псевдонимами ``alias="text.logic"`` и т.п.: в JSON-схеме инструмента и в
query-строке они несут точное имя из спеки, а ``model_dump`` модели
переопределён на ``by_alias=True`` (``toolkit.flatten_params``
сериализует вложенные модели именно через него).

Создание автопоиска (``POST /saved_searches/resumes``): все параметры
операции передаются в query-строке (``query_fields`` со всеми полями
модели; тело операции в hh.ru не используется). Триада
``text.logic``/``text.field``/``text.period`` в операциях автопоисков не
представлена: имя с точкой не может быть параметром верхнего уровня, а
вложенная модель попала бы в JSON-тело вместо query; задокументированное
отступление – полная поддержка триады есть в ``employer_search_resumes``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "employer_resumes"

_ADVANCED_NOTE = (
    " Rare or niche filters are grouped into the nested `advanced` object: "
    "pass only the fields you need, unset fields are not sent."
)

_SPEC_TEXT_LOGIC = (
    "How the text query is matched; id from resume_search_logic dictionary. "
    "Must be passed together with `text.field` and `text.period`."
)


class ResumeSearchAdvanced(BaseModel):
    """Длинный хвост фильтров GET /resumes (двухуровневая схема).

    В запрос попадают только заданные поля (None не отправляется).
    Поля с псевдонимами сериализуются под точным именем из спеки hh.ru
    (например, ``text_logic`` уходит в query как ``text.logic``).
    """

    model_config = ConfigDict(populate_by_name=True)

    text_logic: str | None = Field(None, alias="text.logic", description=_SPEC_TEXT_LOGIC)
    text_field: str | None = Field(
        None,
        alias="text.field",
        description="Where the text query words must occur (comma-separated ids "
        "from resume_search_fields dictionary); part of the text triad.",
    )
    text_period: str | None = Field(
        None,
        alias="text.period",
        description="Experience period qualifier for the text triad "
        "(may be empty when not applicable).",
    )
    text_company_size: str | None = Field(
        None,
        alias="text.company_size",
        description="Company size for work-experience text search: any, small, medium, large.",
    )
    relocation: str | None = Field(
        None,
        description="Relocation readiness filter (resume_search_relocation dictionary); "
        "use with area.",
    )
    date_from: str | None = Field(
        None, description="Search resumes published from this date (YYYY-MM-DD or ISO datetime)."
    )
    date_to: str | None = Field(
        None, description="Search resumes published up to this date; pair with date_from."
    )
    education_level: str | None = Field(
        None,
        description="Education level filter (education_level dictionary). Deprecated by hh.ru "
        "in favour of education_levels, kept for compatibility.",
    )
    education_levels: str | None = Field(
        None,
        description="Required education level(s) (education_level dictionary, comma-separated).",
    )
    skill: str | None = Field(None, description="Key skill id or ids (from skill_set suggests).")
    language: str | None = Field(
        None,
        description="Language knowledge filter, e.g. `eng.c2` (language.level, multiple allowed).",
    )
    work_format: str | None = Field(
        None, description="Work format filter (resume_work_format dictionary, multiple allowed)."
    )
    citizenship: str | None = Field(
        None, description="Citizenship country id or ids (from dict_countries)."
    )
    work_ticket: str | None = Field(
        None, description="Country id or ids where the applicant has a work permit."
    )
    educational_institution: str | None = Field(
        None,
        description="Educational institution name(s) (from educational_institutions suggests).",
    )
    search_in_responses: bool | None = Field(
        None, description="Search only resumes that responded to the current company's vacancies."
    )
    by_text_prefix: bool | None = Field(
        None, description="Match words starting with the text query (prefix search)."
    )
    driver_license_types: str | None = Field(
        None, description="Driver license categories (comma-separated, e.g. B,C)."
    )
    vacancy_id: str | None = Field(
        None,
        description="Vacancy id to search similar resumes for (active or archived own vacancy).",
    )
    folder: str | None = Field(
        None, description="Selected-resume folder id(s); limits the search to these folders."
    )
    include_all_folders: bool | None = Field(
        None,
        description="Search across all favourite folders (true) or without folder limits (false); "
        "mutually exclusive with folder.",
    )
    job_search_status: str | None = Field(
        None, description="Job search status filter (job_search_statuses_employer dictionary)."
    )
    resume: str | None = Field(None, description="Resume id to search similar resumes for.")
    filter_exp_industry: str | None = Field(
        None,
        description="Industry id(s) where the applicant must have experience "
        "(with filter_exp_period).",
    )
    filter_exp_period: str | None = Field(
        None,
        description="Period of industry experience: all_time, last_year, "
        "last_three_years, last_six_years.",
    )
    with_job_search_status: bool | None = Field(
        None, description="Include the applicant's job search status in results."
    )
    district: str | None = Field(None, description="District id (from dict_districts).")
    saved_search_id: str | None = Field(
        None,
        description="Saved search id: run this saved search and refresh its last_used value.",
    )
    search_by_vacancy_id: str | None = Field(
        None, description="Vacancy id: search resumes among responses to this vacancy."
    )
    last_used_timestamp: str | None = Field(
        None,
        description="Unix timestamp of the last saved-search review; with saved_search_id "
        "counts new resumes.",
    )
    last_used: str | None = Field(
        None,
        description="Last review time with timezone, e.g. 2015-11-12T18:06:04+0300; "
        "alternative to last_used_timestamp.",
    )
    business_trip_readiness: str | None = Field(
        None, description="Business trip readiness filter (business_trip_readiness dictionary)."
    )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Отдаёт поля под именами из спеки (``by_alias`` по умолчанию).

        ``toolkit.flatten_params`` вызывает ``model_dump`` без ``by_alias``;
        переопределение даёт query-ключи вида ``text.logic``.
        """
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)


class ResumeSearchParams(BaseModel):
    """GET /resumes: частые параметры верхнего уровня + advanced-хвост."""

    text: str | None = Field(
        None, description="Free-text resume query (supports hh.ru search operators)."
    )
    area: str | None = Field(
        None, description="Region id or ids (comma-separated) from dict_areas."
    )
    age_from: int | None = Field(None, description="Applicant age lower bound (years).")
    age_to: int | None = Field(None, description="Applicant age upper bound (years).")
    period: int | None = Field(
        None, description="Limit search to resumes published within the last N days."
    )
    experience: str | None = Field(
        None, description="Experience filter id(s) (experience dictionary, comma-separated)."
    )
    employment_form: str | None = Field(
        None, description="Employment type id(s) (resume_employment_form dictionary)."
    )
    gender: str | None = Field(None, description="Gender filter id (gender dictionary).")
    label: str | None = Field(
        None,
        description="Extra filter id(s) (resume_search_label dictionary, e.g. only_with_salary).",
    )
    metro: str | None = Field(
        None, description="Metro line or station id or ids (from dict_metro)."
    )
    currency: str | None = Field(
        None, description="Salary currency code (currency.code from dictionaries, e.g. RUR)."
    )
    salary_from: float | None = Field(None, description="Desired salary lower bound.")
    salary_to: float | None = Field(None, description="Desired salary upper bound.")
    professional_role: str | None = Field(
        None, description="Professional role id or ids (from dict_professional_roles)."
    )
    order_by: str | None = Field(
        None,
        description="Result order (resume_search_order dictionary, e.g. relevance, salary_desc).",
    )
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 100, default 20).")
    advanced: ResumeSearchAdvanced | None = Field(
        None,
        description="Rare filters: text triad (text.logic/text.field/text.period), dates, "
        "relocation, languages, folders and more.",
    )


class SavedSearchListParams(BaseModel):
    """GET /saved_searches/resumes: список автопоисков."""

    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 10, default 5).")


class SavedSearchCreateParams(BaseModel):
    """POST /saved_searches/resumes: все параметры уходят в query-строку.

    Триада ``text.logic``/``text.field``/``text.period`` не представлена
    (имя с точкой не бывает параметром верхнего уровня) – см. docstring
    модуля.
    """

    text: str | None = Field(None, description="Free-text resume query for the saved search.")
    age_from: int | None = Field(None, description="Applicant age lower bound (years).")
    age_to: int | None = Field(None, description="Applicant age upper bound (years).")
    area: str | None = Field(
        None, description="Region id or ids (comma-separated) from dict_areas."
    )
    relocation: str | None = Field(
        None,
        description="Relocation readiness (resume_search_relocation dictionary); use with area.",
    )
    period: int | None = Field(
        None, description="Limit the saved search to resumes published within the last N days."
    )
    date_from: str | None = Field(
        None, description="Publish date lower bound (YYYY-MM-DD or ISO datetime)."
    )
    date_to: str | None = Field(None, description="Publish date upper bound; pair with date_from.")
    education_level: str | None = Field(
        None, description="Education level filter (education_level dictionary)."
    )
    employment_form: str | None = Field(
        None, description="Employment type id(s) (resume_employment_form dictionary)."
    )
    experience: str | None = Field(
        None, description="Experience filter id(s) (experience dictionary, comma-separated)."
    )
    skill: str | None = Field(None, description="Key skill id or ids (from skill_set suggests).")
    gender: str | None = Field(None, description="Gender filter id (gender dictionary).")
    label: str | None = Field(
        None, description="Extra filter id(s) (resume_search_label dictionary)."
    )
    language: str | None = Field(
        None, description="Language knowledge filter, e.g. `eng.c2` (language.level)."
    )
    metro: str | None = Field(
        None, description="Metro line or station id or ids (from dict_metro)."
    )
    currency: str | None = Field(None, description="Salary currency code (e.g. RUR).")
    salary_from: float | None = Field(None, description="Desired salary lower bound.")
    salary_to: float | None = Field(None, description="Desired salary upper bound.")
    order_by: str | None = Field(None, description="Result order (resume_search_order dictionary).")
    citizenship: str | None = Field(
        None, description="Citizenship country id or ids (from dict_countries)."
    )
    work_ticket: str | None = Field(
        None, description="Country id or ids where the applicant has a work permit."
    )
    educational_institution: str | None = Field(
        None,
        description="Educational institution name(s) (from educational_institutions suggests).",
    )
    search_in_responses: bool | None = Field(
        None, description="Search only resumes that responded to the current company's vacancies."
    )
    by_text_prefix: bool | None = Field(
        None, description="Match words starting with the text query (prefix search)."
    )
    driver_license_types: str | None = Field(
        None, description="Driver license categories (comma-separated, e.g. B,C)."
    )
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 50, default 10).")
    professional_role: str | None = Field(
        None, description="Professional role id or ids (from dict_professional_roles)."
    )


class SavedSearchIdParams(BaseModel):
    """GET/DELETE /saved_searches/resumes/{id}: один автопоиск."""

    id: str = Field(..., description="Saved search id (from the saved searches list).")


class SavedSearchUpdateParams(BaseModel):
    """PUT /saved_searches/resumes/{id}: смена имени или статуса подписки.

    По спеке в одном запросе передаётся только один из параметров
    (``name`` либо ``subscription``); оба уходят в query-строку.
    """

    id: str = Field(..., description="Saved search id.")
    name: str | None = Field(None, description="New saved search name.")
    subscription: bool | None = Field(
        None, description="Subscription status: true – subscribed, false – unsubscribed."
    )


class SavedSearchAssignParams(BaseModel):
    """PUT /saved_searches/resumes/{saved_search_id}/managers/{manager_id}."""

    saved_search_id: str = Field(..., description="Saved search id to transfer.")
    manager_id: str = Field(..., description="Target manager id (from employer_list_managers).")


class ApplicantCommentsListParams(BaseModel):
    """GET /applicant_comments/{applicant_id}: комментарии к соискателю."""

    applicant_id: str = Field(..., description="Applicant id (the `owner` field of a resume).")
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page.")
    order_by: str | None = Field(
        None, description="Comment order (applicant_comments_order dictionary)."
    )


class ApplicantCommentCreateParams(BaseModel):
    """POST /applicant_comments/{applicant_id}: тело – form-encoded."""

    applicant_id: str = Field(..., description="Applicant id (the `owner` field of a resume).")
    body: dict[str, Any] = Field(
        ...,
        description='Comment fields (form-encoded): {"text": str, "access_type": str} – '
        "access_type ids are listed in applicant_comment_access_type (get_dictionaries).",
    )


class ApplicantCommentUpdateParams(BaseModel):
    """PUT /applicant_comments/{applicant_id}/{comment_id}: тело – form-encoded."""

    applicant_id: str = Field(..., description="Applicant id.")
    comment_id: str = Field(..., description="Comment id (from the comments list).")
    body: dict[str, Any] = Field(
        ...,
        description='Fields to update (form-encoded): {"text": str, "access_type": str}; '
        "omitted fields keep their previous values.",
    )


class ApplicantCommentIdParams(BaseModel):
    """DELETE /applicant_comments/{applicant_id}/{comment_id}."""

    applicant_id: str = Field(..., description="Applicant id.")
    comment_id: str = Field(..., description="Comment id to delete (author only).")


EMPLOYER_SEARCH_RESUMES = make_tool(
    operation_id="GET /resumes",
    name="employer_search_resumes",
    summary="Search resumes as an employer",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ResumeSearchParams,
    docstring_en=(
        "Search the hh.ru resume database (employer access, paid service – "
        "check with employer_get_manager_method_access). Frequent filters "
        "(text, area, salary_from/salary_to, currency, experience, "
        "employment_form, label, order_by, page, per_page and others) are "
        "top-level parameters."
        + _ADVANCED_NOTE
        + " The advanced object also carries the dotted spec parameters "
        "text.logic, text.field, text.period and text.company_size. "
        "Resolve ids first: dict_areas, dict_professional_roles, "
        "dict_metro, get_languages. Results are grouped per applicant."
    ),
)

EMPLOYER_LIST_SAVED_SEARCHES = make_tool(
    operation_id="GET /saved_searches/resumes",
    name="employer_list_saved_searches",
    summary="List saved resume searches",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=SavedSearchListParams,
    docstring_en=(
        "List saved resume searches (auto-searches) of the current employer, "
        "paginated (per_page max 10, default 5)."
    ),
)

EMPLOYER_CREATE_SAVED_SEARCH = make_tool(
    operation_id="POST /saved_searches/resumes",
    name="employer_create_saved_search",
    summary="Create a saved resume search",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=SavedSearchCreateParams,
    query_fields=frozenset(SavedSearchCreateParams.model_fields),
    docstring_en=(
        "Create a saved resume search (auto-search). All filters are query "
        "parameters, the same set as employer_search_resumes minus the "
        "text.logic/text.field/text.period triad (not representable here; "
        "a created search uses the default text matching mode). "
        "Returns 201 with the Location header pointing to the new search."
    ),
)

EMPLOYER_GET_SAVED_SEARCH = make_tool(
    operation_id="GET /saved_searches/resumes/{id}",
    name="employer_get_saved_search",
    summary="Get one saved resume search",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=SavedSearchIdParams,
    docstring_en=(
        "Get one saved resume search by id, including its query, new_items "
        "counter (refreshed hourly) and last_used."
    ),
)

EMPLOYER_UPDATE_SAVED_SEARCH = make_tool(
    operation_id="PUT /saved_searches/resumes/{id}",
    name="employer_update_saved_search",
    summary="Rename a saved search or toggle its subscription",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=SavedSearchUpdateParams,
    query_fields=frozenset({"name", "subscription"}),
    docstring_en=(
        "Update a saved resume search: pass either name (rename) or "
        "subscription (true/false) in one request – the spec forbids both "
        "together. Returns 204 on success."
    ),
)

EMPLOYER_DELETE_SAVED_SEARCH = make_tool(
    operation_id="DELETE /saved_searches/resumes/{id}",
    name="employer_delete_saved_search",
    summary="Delete a saved resume search",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=SavedSearchIdParams,
    docstring_en="Delete a saved resume search by id. Returns 204 on success.",
)

EMPLOYER_ASSIGN_SAVED_SEARCH_MANAGER = make_tool(
    operation_id="PUT /saved_searches/resumes/{saved_search_id}/managers/{manager_id}",
    name="employer_assign_saved_search_manager",
    summary="Transfer a saved search to another manager",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=SavedSearchAssignParams,
    docstring_en=(
        "Transfer a saved resume search to another manager of the company "
        "(manager ids from employer_list_managers). Returns 204 on success."
    ),
)

EMPLOYER_LIST_APPLICANT_COMMENTS = make_tool(
    operation_id="GET /applicant_comments/{applicant_id}",
    name="employer_list_applicant_comments",
    summary="List comments on an applicant",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ApplicantCommentsListParams,
    docstring_en=(
        "List comments on an applicant: own comments plus comments of "
        "colleagues shared with the company (paid access). "
        "order_by ids come from applicant_comments_order (get_dictionaries)."
    ),
)

EMPLOYER_ADD_APPLICANT_COMMENT = make_tool(
    operation_id="POST /applicant_comments/{applicant_id}",
    name="employer_add_applicant_comment",
    summary="Add a comment on an applicant",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=ApplicantCommentCreateParams,
    body_format="form",
    docstring_en=(
        "Add a comment on an applicant (paid access). body (form-encoded): "
        '{"text": str, "access_type": str}; access_type ids are listed '
        "in applicant_comment_access_type (get_dictionaries). Returns 201."
    ),
)

EMPLOYER_UPDATE_APPLICANT_COMMENT = make_tool(
    operation_id="PUT /applicant_comments/{applicant_id}/{comment_id}",
    name="employer_update_applicant_comment",
    summary="Update a comment on an applicant",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=ApplicantCommentUpdateParams,
    body_format="form",
    docstring_en=(
        "Update own comment text or access type (paid access, form-encoded "
        "body); omitted fields of body keep their previous values. "
        "Returns 204."
    ),
)

EMPLOYER_DELETE_APPLICANT_COMMENT = make_tool(
    operation_id="DELETE /applicant_comments/{applicant_id}/{comment_id}",
    name="employer_delete_applicant_comment",
    summary="Delete a comment on an applicant",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=ApplicantCommentIdParams,
    docstring_en=(
        "Delete own comment on an applicant (paid access, author only). Returns 204 on success."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    EMPLOYER_SEARCH_RESUMES,
    EMPLOYER_LIST_SAVED_SEARCHES,
    EMPLOYER_CREATE_SAVED_SEARCH,
    EMPLOYER_GET_SAVED_SEARCH,
    EMPLOYER_UPDATE_SAVED_SEARCH,
    EMPLOYER_DELETE_SAVED_SEARCH,
    EMPLOYER_ASSIGN_SAVED_SEARCH_MANAGER,
    EMPLOYER_LIST_APPLICANT_COMMENTS,
    EMPLOYER_ADD_APPLICANT_COMMENT,
    EMPLOYER_UPDATE_APPLICANT_COMMENT,
    EMPLOYER_DELETE_APPLICANT_COMMENT,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
