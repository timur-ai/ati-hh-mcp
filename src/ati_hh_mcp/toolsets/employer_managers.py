"""Набор «employer_managers»: менеджеры работодателя – 11 операций.

CRUD менеджеров (``/employers/{employer_id}/managers``), справочник типов,
дневной лимит просмотра резюме, доступ к платным методам, предпочтения,
типы публикуемых вакансий (устаревший метод по спеке) и рабочие аккаунты
менеджера (``/manager_accounts/mine``). Статистика откликов менеджера
(``.../negotiations_statistics``) относится к набору
``employer_negotiations`` (волна 3, другой модуль).

Все операции требуют токен hh.ru (``requires_auth=True``); мутации –
с ``confirm=True``. Тела create/update – свободный JSON-объект
(``body: dict[str, Any]``, контракт волны 3); при удалении менеджера
обязательный ``successor_id`` уходит в query-строку.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "employer_managers"


class ManagerListParams(BaseModel):
    """GET /employers/{employer_id}/managers: список менеджеров."""

    employer_id: str = Field(..., description="Employer id (from get_me, employer section).")
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 200, default 200).")
    search_text: str | None = Field(None, description="Search string over manager names.")


class ManagerCreateParams(BaseModel):
    """POST /employers/{employer_id}/managers: тело – JSON-объект."""

    employer_id: str = Field(..., description="Employer id (from get_me, employer section).")
    body: dict[str, Any] = Field(
        ...,
        description="Manager object per hh.ru spec EmployerManagersAddEmployerManager: "
        '{"emails": [str], "manager_type": {"id": str}, "is_admin": bool, ...}.',
    )


class ManagerItemParams(BaseModel):
    """GET /employers/{employer_id}/managers/{manager_id}: один менеджер."""

    employer_id: str = Field(..., description="Employer id.")
    manager_id: str = Field(..., description="Manager id (from employer_list_managers).")


class ManagerUpdateParams(BaseModel):
    """PUT /employers/{employer_id}/managers/{manager_id}: тело – JSON-объект."""

    employer_id: str = Field(..., description="Employer id.")
    manager_id: str = Field(..., description="Manager id to edit.")
    body: dict[str, Any] = Field(
        ...,
        description="Manager fields to update per spec EmployerManagersManagerData: "
        '{"emails": [str], "manager_type": {"id": str}, ...}.',
    )


class ManagerDeleteParams(BaseModel):
    """DELETE /employers/{employer_id}/managers/{manager_id}: successor_id обязателен."""

    employer_id: str = Field(..., description="Employer id.")
    manager_id: str = Field(..., description="Manager id to delete.")
    successor_id: str = Field(
        ...,
        description="Manager id that receives the deleted manager's vacancies, "
        "negotiations, folders, comments and saved searches.",
    )


class EmployerIdParams(BaseModel):
    """GET /employers/{employer_id}/manager_types: справочник типов менеджера."""

    employer_id: str = Field(..., description="Employer id.")


EMPLOYER_LIST_MANAGERS = make_tool(
    operation_id="GET /employers/{employer_id}/managers",
    name="employer_list_managers",
    summary="List employer managers",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ManagerListParams,
    docstring_en=(
        "List managers of the employer (paginated, per_page max 200); "
        "search_text filters by manager name. Manager ids are used by "
        "saved-search transfer, vacancy publishing and manager settings."
    ),
)

EMPLOYER_CREATE_MANAGER = make_tool(
    operation_id="POST /employers/{employer_id}/managers",
    name="employer_create_manager",
    summary="Add an employer manager",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=ManagerCreateParams,
    docstring_en=(
        "Add a manager to the employer. body is a JSON object per spec "
        "(emails, manager_type id from employer_list_manager_types, "
        "is_admin and other fields); returns 201 with the new manager id."
    ),
)

EMPLOYER_GET_MANAGER = make_tool(
    operation_id="GET /employers/{employer_id}/managers/{manager_id}",
    name="employer_get_manager",
    summary="Get one employer manager",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ManagerItemParams,
    docstring_en="Get full info about one manager of the employer.",
)

EMPLOYER_UPDATE_MANAGER = make_tool(
    operation_id="PUT /employers/{employer_id}/managers/{manager_id}",
    name="employer_update_manager",
    summary="Edit an employer manager",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=ManagerUpdateParams,
    docstring_en=(
        "Edit manager parameters: body carries the fields to change "
        "(emails, manager_type and others per spec). Returns 200 on success."
    ),
)

EMPLOYER_DELETE_MANAGER = make_tool(
    operation_id="DELETE /employers/{employer_id}/managers/{manager_id}",
    name="employer_delete_manager",
    summary="Delete an employer manager",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=ManagerDeleteParams,
    docstring_en=(
        "Delete a manager; successor_id (required) receives the manager's "
        "vacancies, negotiations, folders, comments and saved searches. "
        "Deletion is asynchronous: the manager may appear in lists briefly. "
        "Returns 204 on success."
    ),
)

EMPLOYER_LIST_MANAGER_TYPES = make_tool(
    operation_id="GET /employers/{employer_id}/manager_types",
    name="employer_list_manager_types",
    summary="List manager types and permissions",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=EmployerIdParams,
    docstring_en=(
        "Dictionary of manager types with their permission sets – the "
        "manager_type ids for employer_create_manager and "
        "employer_update_manager."
    ),
)

EMPLOYER_GET_MANAGER_RESUME_LIMITS = make_tool(
    operation_id="GET /employers/{employer_id}/managers/{manager_id}/limits/resume",
    name="employer_get_manager_resume_limits",
    summary="Get the manager's daily resume view limit",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ManagerItemParams,
    docstring_en=(
        "Daily resume viewing limit for the manager (a manager may only view their own limit)."
    ),
)

EMPLOYER_GET_MANAGER_METHOD_ACCESS = make_tool(
    operation_id="GET /employers/{employer_id}/managers/{manager_id}/method_access",
    name="employer_get_manager_method_access",
    summary="Check access to paid employer methods",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ManagerItemParams,
    docstring_en=(
        "Paid-method access groups for the manager: resume viewing and "
        "negotiations, resume database search and saved searches, viewing "
        "responded and database-found resumes."
    ),
)

EMPLOYER_GET_MANAGER_SETTINGS = make_tool(
    operation_id="GET /employers/{employer_id}/managers/{manager_id}/settings",
    name="employer_get_manager_settings",
    summary="Get manager preferences",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ManagerItemParams,
    docstring_en=(
        "Manager preferences (default vacancy template, vacancy type and "
        "similar prefill hints). Preferences do not change API behaviour "
        "by themselves – an app may use them for prefilling."
    ),
)

EMPLOYER_GET_MANAGER_VACANCY_TYPES = make_tool(
    operation_id="GET /employers/{employer_id}/managers/{manager_id}/vacancies/available_types",
    name="employer_get_manager_vacancy_types",
    summary="Get vacancy publication types available to the manager",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ManagerItemParams,
    docstring_en=(
        "All vacancy publication types available to the manager (whether "
        "the manager can publish and which types). Deprecated by hh.ru in "
        "favour of the vacancy services list (employer_misc toolset)."
    ),
)

GET_MY_MANAGER_ACCOUNTS = make_tool(
    operation_id="GET /manager_accounts/mine",
    name="get_my_manager_accounts",
    summary="List manager work accounts",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    docstring_en=(
        "Work accounts of the current manager with main/current account "
        "markers. To act under a specific account, its account_id is passed "
        "in the X-Manager-Account-Id header (not set by this MCP server)."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    EMPLOYER_LIST_MANAGERS,
    EMPLOYER_CREATE_MANAGER,
    EMPLOYER_GET_MANAGER,
    EMPLOYER_UPDATE_MANAGER,
    EMPLOYER_DELETE_MANAGER,
    EMPLOYER_LIST_MANAGER_TYPES,
    EMPLOYER_GET_MANAGER_RESUME_LIMITS,
    EMPLOYER_GET_MANAGER_METHOD_ACCESS,
    EMPLOYER_GET_MANAGER_SETTINGS,
    EMPLOYER_GET_MANAGER_VACANCY_TYPES,
    GET_MY_MANAGER_ACCOUNTS,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
