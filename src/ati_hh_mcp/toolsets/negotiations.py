"""Набор «negotiations»: отклики и приглашения – 10 операций.

Список и детали откликов/приглашений, смена состояния и коллекции,
переписка внутри отклика, отметка прочитанным, приглашение на
собеседование и итоги тестов соискателя. Все операции требуют токен
hh.ru (``requires_auth=True``); изменяющие операции – только с явным
``confirm=True``.

Тела запросов (спека описывает их свободными object-схемами) передаются
параметром ``body`` (словарь) и уходят в JSON как есть; ожидаемые ключи
перечислены в описаниях полей. Исключение – приглашение на собеседование
(``POST /negotiations/phone_interview``): спека декларирует
``application/x-www-form-urlencoded``, инструмент отправляет form-тело
(``body_format="form"``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "negotiations"


class ListNegotiationsParams(BaseModel):
    """GET /negotiations: список откликов/приглашений текущего пользователя."""

    status: str | None = Field(
        None,
        description="Only negotiations in this status (applicant_negotiation_status dictionary).",
    )
    vacancy_id: str | None = Field(None, description="Filter negotiations by vacancy id.")
    order_by: str | None = Field(
        None, description="Sort field (negotiations_order dictionary values)."
    )
    order: str | None = Field(None, description="Sort direction: asc or desc.")
    has_updates: bool | None = Field(
        None, description="Only negotiations with unread incoming messages."
    )
    with_job_search_status: bool | None = Field(
        None, description="Include the candidate's job search status."
    )
    with_generated_collections: bool | None = Field(
        None, description="Include generated collections of the negotiation list."
    )
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 50).")


class NegotiationIdParams(BaseModel):
    """GET /negotiations/{id}: один отклик/приглашение."""

    id: str = Field(..., description="Negotiation (topic) id.")


class UpdateNegotiationParams(BaseModel):
    """PUT /negotiations/{id}: действие по откликам/приглашениям коллекции."""

    id: str = Field(
        ...,
        description="Collection id (the {id} part of the actions URL returned by the API).",
    )
    body: dict[str, Any] = Field(
        ...,
        description=(
            'JSON body of the action, e.g. {"topic_id": "123", "message": "text", '
            '"send_sms": false}; required body arguments differ per action '
            "(see actions[].arguments of the negotiation)."
        ),
    )


class MoveNegotiationParams(BaseModel):
    """PUT /negotiations/{collection_name}/{nid}: смена состояния отклика."""

    collection_name: str = Field(
        ...,
        description="Target collection name (from actions[].url of the negotiation list).",
    )
    nid: str = Field(..., description="Negotiation (topic) id.")
    body: dict[str, Any] | None = Field(
        None,
        description='Optional JSON body of the state change, e.g. {"message": "text"}.',
    )


class ListNegotiationMessagesParams(BaseModel):
    """GET /negotiations/{nid}/messages: переписка отклика/приглашения."""

    nid: str = Field(..., description="Negotiation (topic) id.")
    with_text_only: bool | None = Field(
        None, description="Only messages with text content."
    )
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 50).")


class SendNegotiationMessageParams(BaseModel):
    """POST /negotiations/{nid}/messages: отправка сообщения в переписку."""

    nid: str = Field(..., description="Negotiation (topic) id.")
    body: dict[str, Any] = Field(
        ...,
        description='JSON body: {"message": "message text"}.',
    )


class ListCollectionNegotiationsParams(BaseModel):
    """GET /negotiations/response: отклики коллекции «Все неразобранные»."""

    vacancy_id: str = Field(..., description="Vacancy id whose responses are listed.")
    order_by: str | None = Field(
        None, description="Sort type (order_types field of the collections list)."
    )
    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Items per page (max 50).")
    age_from: str | None = Field(None, description="Applicant age lower bound (years).")
    age_to: str | None = Field(None, description="Applicant age upper bound (years).")
    area: str | None = Field(
        None, description="Region id or comma-separated ids (dict_areas)."
    )
    citizenship: str | None = Field(
        None, description="Citizenship country id or comma-separated ids (dict_countries)."
    )
    currency: str | None = Field(
        None, description="Salary currency code (dictionaries currency field, e.g. RUR)."
    )
    driver_license_types: str | None = Field(
        None, description="Driver license categories, comma-separated (dictionaries)."
    )
    educational_institution: str | None = Field(
        None, description="Educational institution id or comma-separated ids."
    )
    education_level: str | None = Field(
        None, description="Education level filter (education_level dictionary value)."
    )
    education_levels: str | None = Field(
        None, description="Required education levels, comma-separated (dictionaries)."
    )
    experience: str | None = Field(
        None, description="Experience filter id or comma-separated ids (dictionaries)."
    )
    gender: str | None = Field(
        None, description="Applicant gender filter (gender dictionary value)."
    )
    language: str | None = Field(
        None,
        description="Language skill filter, format language.level (e.g. eng.b2), "
        "comma-separated for several languages.",
    )
    relocation: str | None = Field(
        None,
        description="Relocation readiness (resume_search_relocation dictionary value); "
        "use together with area.",
    )
    salary_from: float | None = Field(
        None, description="Desired salary lower bound (combined with currency)."
    )
    salary_to: float | None = Field(
        None, description="Desired salary upper bound (combined with currency)."
    )
    search_radius_meters: int | None = Field(
        None, description="Distance to the candidate in meters."
    )
    search_text: str | None = Field(None, description="Free-text search query.")
    show_only_new_responses: bool | None = Field(
        None, description='Only unseen responses of the "/response" collection.'
    )
    show_only_with_vehicle: bool | None = Field(
        None, description="Only applicants with a personal vehicle."
    )
    show_only_with_self_employment: bool | None = Field(
        None, description="Only applicants with registered self-employment."
    )
    show_only_with_medical_book: bool | None = Field(
        None, description="Only applicants with a medical certificate."
    )
    show_only_new: bool | None = Field(
        None, description="Only negotiations with unread messages."
    )


class MarkNegotiationsReadParams(BaseModel):
    """POST /negotiations/read: отметить отклики прочитанными."""

    body: dict[str, Any] = Field(
        ...,
        description=(
            'JSON body: {"topic_id": "123"} – negotiation ids belonging '
            "to one vacancy (up to 50)."
        ),
    )


class RequestPhoneInterviewParams(BaseModel):
    """POST /negotiations/phone_interview: приглашение соискателя на вакансию."""

    body: dict[str, Any] = Field(
        ...,
        description=(
            'Form body: {"resume_id": "123", "vacancy_id": "456", '
            '"message": "invitation text", "send_sms": false} '
            "(form-encoded); resume_id and vacancy_id are required."
        ),
    )


class NegotiationTestSolutionParams(BaseModel):
    """GET /negotiations/{nid}/test/solution: итоги тестов соискателя."""

    nid: str = Field(..., description="Negotiation (topic) id.")


LIST_NEGOTIATIONS = make_tool(
    operation_id="GET /negotiations",
    name="list_negotiations",
    summary="List negotiations (responses and invitations)",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ListNegotiationsParams,
    docstring_en=(
        "List negotiations (responses and invitations) of the current "
        "user. Filter by status, vacancy or unread updates; ordered by "
        "last update (newest first) by default. The response contains "
        "collections with actions URLs used by other negotiation tools."
    ),
)

GET_NEGOTIATION = make_tool(
    operation_id="GET /negotiations/{id}",
    name="get_negotiation",
    summary="Get one negotiation by id",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=NegotiationIdParams,
    docstring_en=(
        "Get full information about a single negotiation (response or "
        "invitation) by its id, including messages URL and available "
        "state actions."
    ),
)

UPDATE_NEGOTIATION = make_tool(
    operation_id="PUT /negotiations/{id}",
    name="update_negotiation",
    summary="Apply an action to negotiations of a collection",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=UpdateNegotiationParams,
    docstring_en=(
        "Apply a collection action (for example invite or decline) to "
        "one or more negotiations. The {id} path value and required "
        "body arguments (topic_id, message, send_sms and others) come "
        "from actions[].url and actions[].arguments of the negotiation "
        "list. Mutation: requires confirm=True."
    ),
)

MOVE_NEGOTIATION = make_tool(
    operation_id="PUT /negotiations/{collection_name}/{nid}",
    name="move_negotiation",
    summary="Move a negotiation to another collection or state",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=MoveNegotiationParams,
    docstring_en=(
        "Change the employer or applicant state of a negotiation by "
        "moving it to another collection (for example from response to "
        "invitation). collection_name and nid come from the actions URL "
        "of the negotiation; an optional message can be attached. "
        "Mutation: requires confirm=True."
    ),
)

LIST_NEGOTIATION_MESSAGES = make_tool(
    operation_id="GET /negotiations/{nid}/messages",
    name="list_negotiation_messages",
    summary="List messages of a negotiation",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ListNegotiationMessagesParams,
    docstring_en=(
        "List all messages of a negotiation (response or invitation) "
        "thread. Note: hh.ru considers negotiation messaging legacy and "
        "recommends chats; use with_text_only to skip service messages."
    ),
)

SEND_NEGOTIATION_MESSAGE = make_tool(
    operation_id="POST /negotiations/{nid}/messages",
    name="send_negotiation_message",
    summary="Send a message in a negotiation",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=SendNegotiationMessageParams,
    docstring_en=(
        "Send a new message inside a negotiation thread. Sending is "
        "possible while the conversation is open (see the hh.ru rules "
        "for negotiations). Mutation: requires confirm=True."
    ),
)

LIST_COLLECTION_NEGOTIATIONS = make_tool(
    operation_id="GET /negotiations/response",
    name="list_collection_negotiations",
    summary="List the response collection of a vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ListCollectionNegotiationsParams,
    docstring_en=(
        "List negotiations of the unsorted responses collection "
        '("/response") of a vacancy with resume-like filters: area, '
        "experience, education, salary range, age and others. The same "
        "URL pattern serves other collections: replace the last path "
        "segment with the collection id from the collections list."
    ),
)

MARK_NEGOTIATIONS_READ = make_tool(
    operation_id="POST /negotiations/read",
    name="mark_negotiations_read",
    summary="Mark negotiations as read",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=MarkNegotiationsReadParams,
    docstring_en=(
        "Mark negotiations as read. topic_id values in the body must "
        "belong to one vacancy (up to 50 ids). Mutation: requires "
        "confirm=True."
    ),
)

REQUEST_PHONE_INTERVIEW = make_tool(
    operation_id="POST /negotiations/phone_interview",
    name="request_phone_interview",
    summary="Invite an applicant to a vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=RequestPhoneInterviewParams,
    body_format="form",
    docstring_en=(
        "Invite an applicant to a vacancy by resume: creates an "
        "invitation negotiation, optionally sends an email message and "
        "an SMS notification. resume_id and vacancy_id are required in "
        "the body (sent form-encoded per the vendor spec). Mutation: "
        "requires confirm=True."
    ),
)

GET_NEGOTIATION_TEST_SOLUTION = make_tool(
    operation_id="GET /negotiations/{nid}/test/solution",
    name="get_negotiation_test_solution",
    summary="Get test results of a negotiation",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=NegotiationTestSolutionParams,
    docstring_en=(
        "Get the results of tests completed by the applicant of a "
        "negotiation (attached to the vacancy)."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    LIST_NEGOTIATIONS,
    GET_NEGOTIATION,
    UPDATE_NEGOTIATION,
    MOVE_NEGOTIATION,
    LIST_NEGOTIATION_MESSAGES,
    SEND_NEGOTIATION_MESSAGE,
    LIST_COLLECTION_NEGOTIATIONS,
    MARK_NEGOTIATIONS_READ,
    REQUEST_PHONE_INTERVIEW,
    GET_NEGOTIATION_TEST_SOLUTION,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
