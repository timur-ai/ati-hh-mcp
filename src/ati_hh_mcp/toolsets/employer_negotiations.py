"""Набор «employer_negotiations»: отклики работодателя – 5 операций.

Шаблоны ответов соискателю (``mail_templates``), история откликов по
резюме и статистика откликов компании/менеджера. Все инструменты
требуют токен работодателя hh.ru; изменение шаблона – мутация с
``confirm=True``. Тело изменения шаблона передаётся параметром ``body``
(схема MailTemplatesMailTemplateInput: обязательное поле ``text``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "employer_negotiations"


class MailTemplatesParams(BaseModel):
    """GET /employers/{employer_id}/mail_templates."""

    employer_id: str = Field(..., description="Employer id.")


class UpdateMailTemplateParams(BaseModel):
    """PUT /employers/{employer_id}/mail_templates/{template_id}."""

    employer_id: str = Field(..., description="Employer id.")
    template_id: str = Field(..., description="Response template id, e.g. invite_mail.")
    body: dict[str, Any] = Field(
        ...,
        description=(
            'Template fields, e.g. {"text": "Здравствуйте, [Name]! ..."} '
            "(required text; [Name], [Company], [Vacancy] placeholders "
            "are substituted by hh.ru)."
        ),
    )


class ResumeNegotiationsHistoryParams(BaseModel):
    """GET /resumes/{resume_id}/negotiations_history."""

    resume_id: str = Field(..., description="Resume id.")


class NegotiationsStatisticsParams(BaseModel):
    """GET /employers/{employer_id}/negotiations_statistics."""

    employer_id: str = Field(..., description="Employer id.")


class ManagerNegotiationsStatisticsParams(BaseModel):
    """GET /employers/{employer_id}/managers/{manager_id}/negotiations_statistics."""

    employer_id: str = Field(..., description="Employer id.")
    manager_id: str = Field(..., description="Manager id.")


EMPLOYER_LIST_MAIL_TEMPLATES = make_tool(
    operation_id="GET /employers/{employer_id}/mail_templates",
    name="employer_list_mail_templates",
    summary="List response mail templates of an employer",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=MailTemplatesParams,
    docstring_en=(
        "List response templates available to the employer for "
        "replying to candidates (invite, rejection and others)."
    ),
)

EMPLOYER_UPDATE_MAIL_TEMPLATE = make_tool(
    operation_id="PUT /employers/{employer_id}/mail_templates/{template_id}",
    name="employer_update_mail_template",
    summary="Edit a response mail template",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=UpdateMailTemplateParams,
    docstring_en=(
        "Edit the text of a response template: the new text goes into "
        '`body`, e.g. {"text": "..."}. Mutation: requires confirm=True.'
    ),
)

EMPLOYER_GET_RESUME_NEGOTIATIONS_HISTORY = make_tool(
    operation_id="GET /resumes/{resume_id}/negotiations_history",
    name="employer_get_resume_negotiations_history",
    summary="Get negotiation history for a resume",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ResumeNegotiationsHistoryParams,
    docstring_en=(
        "Get the history of responses and invitations for the resume "
        "visible to the employer."
    ),
)

EMPLOYER_GET_NEGOTIATIONS_STATISTICS = make_tool(
    operation_id="GET /employers/{employer_id}/negotiations_statistics",
    name="employer_get_negotiations_statistics",
    summary="Get negotiations statistics of an employer",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=NegotiationsStatisticsParams,
    docstring_en=(
        "Get aggregated responses/invitations statistics for the whole "
        "company."
    ),
)

EMPLOYER_GET_MANAGER_NEGOTIATIONS_STATISTICS = make_tool(
    operation_id="GET /employers/{employer_id}/managers/{manager_id}"
    "/negotiations_statistics",
    name="employer_get_manager_negotiations_statistics",
    summary="Get negotiations statistics of a manager",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ManagerNegotiationsStatisticsParams,
    docstring_en=(
        "Get responses/invitations statistics for one manager of the "
        "company."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    EMPLOYER_LIST_MAIL_TEMPLATES,
    EMPLOYER_UPDATE_MAIL_TEMPLATE,
    EMPLOYER_GET_RESUME_NEGOTIATIONS_HISTORY,
    EMPLOYER_GET_NEGOTIATIONS_STATISTICS,
    EMPLOYER_GET_MANAGER_NEGOTIATIONS_STATISTICS,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
