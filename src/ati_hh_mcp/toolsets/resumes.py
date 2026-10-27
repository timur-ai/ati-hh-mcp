"""Набор «resumes»: просмотр резюме – 2 операции.

Просмотр резюме (своего или доступного работодателю) и получение
номера телефона соискателя через колл-трекинг hh.ru. Обе операции
требуют токен hh.ru (``requires_auth=True``).

Полная история откликов по резюме (GET /resumes/{resume_id}/
negotiations_history) в этот набор не входит и распределяется lead-ом
отдельно (см. отчёт волны 3).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "resumes"


class GetResumeParams(BaseModel):
    """GET /resumes/{resume_id}: просмотр резюме."""

    resume_id: str = Field(..., description="Resume id or resume hash.")
    with_negotiations_history: bool | None = Field(
        None,
        description="Include the negotiations_history.vacancies field in the response.",
    )
    with_creds: bool | None = Field(
        None, description="Include the candidate credentials (contacts) field."
    )
    with_job_search_status: bool | None = Field(
        None, description="Include the candidate's job search status."
    )


class GetResumePhoneParams(BaseModel):
    """GET /resumes/{resume_id}/phone: телефон через колл-трекинг."""

    resume_id: str = Field(..., description="Resume id or resume hash.")


GET_RESUME = make_tool(
    operation_id="GET /resumes/{resume_id}",
    name="get_resume",
    summary="Get a resume by id",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=GetResumeParams,
    docstring_en=(
        "Get a resume by id or hash: own resume for an applicant or an "
        "accessible resume for an employer. Optional flags add contact "
        "credentials, job search status and negotiation history."
    ),
)

GET_RESUME_PHONE = make_tool(
    operation_id="GET /resumes/{resume_id}/phone",
    name="get_resume_phone",
    summary="Get a resume phone number (call tracking)",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=GetResumePhoneParams,
    docstring_en=(
        "Get the phone number of a resume through hh.ru call tracking "
        "(employer side; the call is logged by hh.ru)."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    GET_RESUME,
    GET_RESUME_PHONE,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
