"""Набор «chats»: чаты hh.ru (общие для соискателя и работодателя) – 14 операций.

Список чатов и счётчики непрочитанных, сообщения (просмотр/отправка/
правка/удаление/отметка прочитанным), участники, выход из чата,
управление правом записи и файловые вложения (условия и ссылка на
загрузку). Все операции требуют токен hh.ru (``requires_auth=True``);
изменяющие операции – только с явным ``confirm=True``.

Тела запросов передаются параметром ``body`` (словарь) и уходят в JSON;
``applicant_write_possibility`` у права записи – query-параметр
(``query_fields``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import toolkit
from ..toolkit import ClientFactory, make_tool

TOOLSET_NAME = "chats"


class ListChatsParams(BaseModel):
    """GET /common/chats: список чатов."""

    page: int | None = Field(None, description="Page number, zero-based.")
    per_page: int | None = Field(None, description="Chats per page (max 100, default 20).")
    filter_unread: bool | None = Field(None, description="Only unread chats.")
    filter_has_text_message: bool | None = Field(
        None, description="Only chats with text messages (employer side)."
    )
    vacancy_status: str | None = Field(
        None, description="Filter by related vacancy status (default: all)."
    )
    filter_with_vacancy_ids: str | None = Field(
        None,
        description="Only chats of these vacancy ids, format: bracketed csv, e.g. [1,2,3].",
    )


class CreateChatFileUploadLinkParams(BaseModel):
    """POST /common/chats/files/upload_links: ссылка на загрузку файла."""

    body: dict[str, Any] | None = Field(
        None,
        description=(
            "Optional JSON body describing the file to upload (free-form in the "
            "hh.ru spec); the returned link accepts a multipart POST with field "
            "'file'."
        ),
    )


class CreateChatWithoutVacancyParams(BaseModel):
    """POST /common/chats/without_vacancy: чат вне вакансии."""

    body: dict[str, Any] = Field(
        ...,
        description=(
            'JSON body: {"resume_hash": "hash", "first_message": "text"}; '
            "resume_hash is required, first_message is optional."
        ),
    )


class ChatIdParams(BaseModel):
    """PUT /common/chats/{chat_id}/leave: выход из чата."""

    chat_id: str = Field(..., description="Chat id.")


class MarkChatMessageReadParams(BaseModel):
    """PUT /common/chats/{chat_id}/message/{message_id}/read: отметка прочитанным."""

    chat_id: str = Field(..., description="Chat id.")
    message_id: str = Field(..., description="Message id to mark as last viewed.")


class ListChatMessagesParams(BaseModel):
    """GET /common/chats/{chat_id}/messages: сообщения чата."""

    chat_id: str = Field(..., description="Chat id.")
    start_message_id: str | None = Field(
        None,
        description="Message id to start from (default: first message for "
        "order=next, last for order=prev).",
    )
    limit: int | None = Field(None, description="Max messages to return (default 10).")
    order: str | None = Field(
        None, description="Selection order from start_message_id: next or prev."
    )


class SendChatMessageParams(BaseModel):
    """POST /common/chats/{chat_id}/messages: отправка сообщения в чат."""

    chat_id: str = Field(..., description="Chat id.")
    body: dict[str, Any] = Field(
        ...,
        description=(
            'JSON body: text message {"text": "message text"} or file message '
            '{"file_upload_id": "upload id"} (from create_chat_file_upload_link).'
        ),
    )


class UpdateChatMessageParams(BaseModel):
    """PUT /common/chats/{chat_id}/messages/{message_id}: правка сообщения."""

    chat_id: str = Field(..., description="Chat id.")
    message_id: str = Field(..., description="Message id to edit.")
    body: dict[str, Any] = Field(
        ..., description='JSON body: {"text": "new message text"} (1..20000 chars).'
    )


class DeleteChatMessageParams(BaseModel):
    """DELETE /common/chats/{chat_id}/messages/{message_id}: удаление сообщения."""

    chat_id: str = Field(..., description="Chat id.")
    message_id: str = Field(..., description="Message id to delete.")


class GetChatParticipantsParams(BaseModel):
    """GET /common/chats/{chat_id}/participants: участники чата."""

    chat_id: str = Field(..., description="Chat id.")


class UpdateChatParticipantsParams(BaseModel):
    """PUT /common/chats/{chat_id}/participants: состав участников-менеджеров."""

    chat_id: str = Field(..., description="Chat id.")
    body: dict[str, Any] = Field(
        ...,
        description='JSON body: {"id": "manager id"} – manager to add to the chat.',
    )


class SetChatWritePossibilityParams(BaseModel):
    """PUT /common/chats/{chat_id}/write_possibility: право записи соискателя."""

    chat_id: str = Field(..., description="Chat id.")
    applicant_write_possibility: bool = Field(
        ...,
        description="Whether the applicant may write messages in the chat "
        "(sent as a query parameter).",
    )
    body: dict[str, Any] | None = Field(
        None, description="Optional JSON body of the request (free-form in the hh.ru spec)."
    )


LIST_CHATS = make_tool(
    operation_id="GET /common/chats",
    name="list_chats",
    summary="List chats",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ListChatsParams,
    docstring_en=(
        "List chats of the current user (applicant or employer) with "
        "pagination and filters: unread only, with text messages, by "
        "vacancy status or explicit vacancy ids."
    ),
)

GET_UNREAD_COUNTERS = make_tool(
    operation_id="GET /common/chats/counters/unread",
    name="get_unread_counters",
    summary="Get unread chat counters",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    docstring_en=(
        "Get the number of unread chats for the current user (total "
        "and with new messages)."
    ),
)

GET_CHAT_FILE_CONDITIONS = make_tool(
    operation_id="GET /common/chats/files/conditions",
    name="get_chat_file_conditions",
    summary="Get chat file upload conditions",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    docstring_en=(
        "Get conditions for files attached to chat messages: allowed "
        "formats, size limits and other constraints."
    ),
)

CREATE_CHAT_FILE_UPLOAD_LINK = make_tool(
    operation_id="POST /common/chats/files/upload_links",
    name="create_chat_file_upload_link",
    summary="Create a chat file upload link",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=CreateChatFileUploadLinkParams,
    docstring_en=(
        "Create a one-time upload link for a chat file attachment. "
        "Upload the file with a multipart POST (field 'file') to the "
        "returned URL, then send the message with the received "
        "file_upload_id (see send_chat_message). Check "
        "get_chat_file_conditions first. Mutation: requires confirm=True."
    ),
)

CREATE_CHAT_WITHOUT_VACANCY = make_tool(
    operation_id="POST /common/chats/without_vacancy",
    name="create_chat_without_vacancy",
    summary="Create a chat without a vacancy",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=CreateChatWithoutVacancyParams,
    docstring_en=(
        "Get an existing chat or create a new one bound to a resume "
        "without a specific vacancy (resume_hash is required, an "
        "optional first_message opens the conversation). Mutation: "
        "requires confirm=True."
    ),
)

LEAVE_CHAT = make_tool(
    operation_id="PUT /common/chats/{chat_id}/leave",
    name="leave_chat",
    summary="Leave a chat",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=ChatIdParams,
    docstring_en=(
        "Leave the given chat. Mutation: requires confirm=True."
    ),
)

MARK_CHAT_MESSAGE_READ = make_tool(
    operation_id="PUT /common/chats/{chat_id}/message/{message_id}/read",
    name="mark_chat_message_read",
    summary="Mark a chat message as last viewed",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=MarkChatMessageReadParams,
    docstring_en=(
        "Mark the message as the last viewed one in the chat (updates "
        "unread counters). Mutation: requires confirm=True."
    ),
)

LIST_CHAT_MESSAGES = make_tool(
    operation_id="GET /common/chats/{chat_id}/messages",
    name="list_chat_messages",
    summary="List chat messages",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=ListChatMessagesParams,
    docstring_en=(
        "List messages of a chat, starting from start_message_id in "
        "the given order (next or prev) with a limit (default 10)."
    ),
)

SEND_CHAT_MESSAGE = make_tool(
    operation_id="POST /common/chats/{chat_id}/messages",
    name="send_chat_message",
    summary="Send a message to a chat",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=SendChatMessageParams,
    docstring_en=(
        "Send a message to a chat: either a text message "
        '({"text": "..."}) or a file ({"file_upload_id": "..."} from '
        "create_chat_file_upload_link). Mutation: requires confirm=True."
    ),
)

UPDATE_CHAT_MESSAGE = make_tool(
    operation_id="PUT /common/chats/{chat_id}/messages/{message_id}",
    name="update_chat_message",
    summary="Edit a chat message",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=UpdateChatMessageParams,
    docstring_en=(
        "Edit the text of your own message in a chat. Mutation: "
        "requires confirm=True."
    ),
)

DELETE_CHAT_MESSAGE = make_tool(
    operation_id="DELETE /common/chats/{chat_id}/messages/{message_id}",
    name="delete_chat_message",
    summary="Delete a chat message",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=DeleteChatMessageParams,
    docstring_en=(
        "Delete your own message from a chat. Mutation: requires confirm=True."
    ),
)

GET_CHAT_PARTICIPANTS = make_tool(
    operation_id="GET /common/chats/{chat_id}/participants",
    name="get_chat_participants",
    summary="Get chat participants",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=False,
    param_model=GetChatParticipantsParams,
    docstring_en=(
        "List participants of the chat: the applicant and employer "
        "managers involved in the conversation."
    ),
)

UPDATE_CHAT_PARTICIPANTS = make_tool(
    operation_id="PUT /common/chats/{chat_id}/participants",
    name="update_chat_participants",
    summary="Change chat participants",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=UpdateChatParticipantsParams,
    docstring_en=(
        "Add an employer manager to the chat (body: manager id). "
        "Mutation: requires confirm=True."
    ),
)

SET_CHAT_WRITE_POSSIBILITY = make_tool(
    operation_id="PUT /common/chats/{chat_id}/write_possibility",
    name="set_chat_write_possibility",
    summary="Set whether the applicant can write in a chat",
    toolset=TOOLSET_NAME,
    requires_auth=True,
    is_mutation=True,
    param_model=SetChatWritePossibilityParams,
    query_fields={"applicant_write_possibility"},
    docstring_en=(
        "Enable or disable the applicant's right to write messages in "
        "the chat (employer side; applicant_write_possibility is sent "
        "as a query parameter). Mutation: requires confirm=True."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (
    LIST_CHATS,
    GET_UNREAD_COUNTERS,
    GET_CHAT_FILE_CONDITIONS,
    CREATE_CHAT_FILE_UPLOAD_LINK,
    CREATE_CHAT_WITHOUT_VACANCY,
    LEAVE_CHAT,
    MARK_CHAT_MESSAGE_READ,
    LIST_CHAT_MESSAGES,
    SEND_CHAT_MESSAGE,
    UPDATE_CHAT_MESSAGE,
    DELETE_CHAT_MESSAGE,
    GET_CHAT_PARTICIPANTS,
    UPDATE_CHAT_PARTICIPANTS,
    SET_CHAT_WRITE_POSSIBILITY,
)


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает все инструменты набора к серверу (контракт волны 2)."""
    if client_factory is not None:
        toolkit.set_client_factory(client_factory)
    for tool in _TOOLS:
        mcp.tool(tool)
