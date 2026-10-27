"""Тесты реестра и шаблона инструментов (toolkit)."""

from __future__ import annotations

import inspect
import json
from typing import Any

import pytest
from pydantic import BaseModel

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.registry import REGISTRY, Registry, ToolEntry

from ..conftest import MockHH, make_config


def _bound_client(mock: MockHH) -> HHClient:
    return HHClient(make_config(), transport=mock.transport)


class _DemoParams(BaseModel):
    """Параметры тестовой операции."""

    text: str | None = None
    page: int | None = None


# Отдельный реестр, чтобы не трогать глобальный.
def test_registry_register_and_lookup() -> None:
    registry = Registry()
    entry = ToolEntry(
        name="demo_get",
        operation_id="GET /demo",
        toolset="demo",
        requires_auth=False,
        is_mutation=False,
    )
    registry.register(entry)
    assert registry.get("demo_get") is entry
    assert registry.get_by_operation("GET /demo") is entry
    assert registry.all() == (entry,)
    assert registry.by_toolset("demo") == (entry,)
    assert registry.by_toolset("other") == ()


def test_registry_duplicate_name_rejected() -> None:
    registry = Registry()
    registry.register(
        ToolEntry("a", "GET /a", "demo", False, False)
    )
    with pytest.raises(ValueError, match="уже зарегистрирован"):
        registry.register(ToolEntry("a", "GET /b", "demo", False, False))


def test_registry_duplicate_operation_rejected() -> None:
    registry = Registry()
    registry.register(ToolEntry("a", "GET /a", "demo", False, False))
    with pytest.raises(ValueError, match="уже занята"):
        registry.register(ToolEntry("b", "GET /a", "demo", False, False))


def test_make_tool_registers_in_global_registry() -> None:
    tool = toolkit.make_tool(
        operation_id="GET /unit_demo",
        name="unit_demo_get",
        summary="Unit demo",
        toolset="unit_test",
        requires_auth=False,
        is_mutation=False,
        param_model=_DemoParams,
    )
    entry = REGISTRY.get("unit_demo_get")
    assert entry is not None
    assert entry.operation_id == "GET /unit_demo"
    assert entry.toolset == "unit_test"
    assert entry.requires_auth is False
    assert entry.is_mutation is False
    assert REGISTRY.get_by_operation("GET /unit_demo") is entry
    # Плоская сигнатура из полей модели.
    signature = inspect.signature(tool)
    assert list(signature.parameters) == ["text", "page"]


async def test_make_tool_flat_signature_and_call(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": [1]}
    toolkit.set_client_factory(lambda: _bound_client(mock_hh))
    tool = toolkit.make_tool(
        operation_id="GET /flat_demo",
        name="unit_flat_get",
        summary="Flat params demo",
        toolset="unit_test",
        requires_auth=False,
        is_mutation=False,
        param_model=_DemoParams,
    )
    result = await tool(text="python", page=3)
    assert result == {"items": [1]}
    request = mock_hh.requests[0]
    assert request.url.path == "/flat_demo"
    assert request.url.params["text"] == "python"
    assert request.url.params["page"] == "3"


async def test_mutation_requires_confirm(mock_hh: MockHH) -> None:
    calls: list[str] = []

    def factory() -> HHClient:
        calls.append("created")
        return _bound_client(mock_hh)

    toolkit.set_client_factory(factory)
    tool = toolkit.make_tool(
        operation_id="POST /mutation_demo",
        name="unit_mutation_do",
        summary="Mutation demo",
        toolset="unit_test",
        requires_auth=True,
        is_mutation=True,
        param_model=_DemoParams,
    )
    signature = inspect.signature(tool)
    assert list(signature.parameters) == ["text", "page", "confirm"]

    # Без confirm – структурированная ошибка, HTTP не выполняется.
    with pytest.raises(HHError) as excinfo:
        await tool(text="x")
    assert excinfo.value.code == "confirm_required"
    assert "confirm=True" in excinfo.value.description
    assert calls == []

    # С confirm – запрос уходит.
    await tool(text="x", confirm=True)
    assert mock_hh.requests[-1].method == "POST"
    assert calls == ["created"]


# --- query_fields: разделение query/тело для мутаций (волна 3) -------------


class _MutationWithQueryParams(BaseModel):
    """Модель мутации с query-параметром (ignore_duplicates) и телом."""

    ignore_duplicates: bool | None = None
    name: str | None = None
    employer_id: str | None = None


async def test_post_query_fields_split_query_and_body(mock_hh: MockHH) -> None:
    toolkit.set_client_factory(lambda: _bound_client(mock_hh))
    tool = toolkit.make_tool(
        operation_id="POST /query_split_demo",
        name="unit_query_split_post",
        summary="Query split demo",
        toolset="unit_test",
        requires_auth=True,
        is_mutation=True,
        param_model=_MutationWithQueryParams,
        query_fields={"ignore_duplicates"},
    )
    await tool(
        ignore_duplicates=True, name="Backend", employer_id="777", confirm=True
    )
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    # query_fields уходит в query-строку.
    assert dict(request.url.params) == {"ignore_duplicates": "true"}
    # Остальное – в JSON-тело.
    assert json.loads(request.read()) == {"name": "Backend", "employer_id": "777"}


async def test_put_query_fields_with_path_param(mock_hh: MockHH) -> None:
    toolkit.set_client_factory(lambda: _bound_client(mock_hh))
    tool = toolkit.make_tool(
        operation_id="PUT /query_put_demo/{id}",
        name="unit_query_split_put",
        summary="Query split put demo",
        toolset="unit_test",
        requires_auth=True,
        is_mutation=True,
        param_model=_MutationWithQueryParams,
        query_fields={"ignore_duplicates"},
    )
    await tool(id="42", ignore_duplicates=False, name="X", confirm=True)
    request = mock_hh.requests[-1]
    assert request.url.path == "/query_put_demo/42"  # path-параметр подставлен.
    assert dict(request.url.params) == {"ignore_duplicates": "false"}
    assert json.loads(request.read()) == {"name": "X"}


async def test_post_query_fields_only_query_sends_no_body(mock_hh: MockHH) -> None:
    """Все заданные поля ушли в query – тело не отправляется вовсе."""
    toolkit.set_client_factory(lambda: _bound_client(mock_hh))
    tool = toolkit.make_tool(
        operation_id="POST /query_only_demo",
        name="unit_query_only_post",
        summary="Query only demo",
        toolset="unit_test",
        requires_auth=True,
        is_mutation=True,
        param_model=_MutationWithQueryParams,
        query_fields={"ignore_duplicates", "employer_id"},
    )
    await tool(ignore_duplicates=True, employer_id="7", confirm=True)
    request = mock_hh.requests[-1]
    assert dict(request.url.params) == {"ignore_duplicates": "true", "employer_id": "7"}
    assert request.read() == b""  # пустое тело не кодируется как {}


async def test_post_without_query_fields_keeps_body_only(mock_hh: MockHH) -> None:
    """Без query_fields поведение прежнее: всё в теле, query пуст."""
    toolkit.set_client_factory(lambda: _bound_client(mock_hh))
    tool = toolkit.make_tool(
        operation_id="POST /body_only_demo",
        name="unit_body_only_post",
        summary="Body only demo",
        toolset="unit_test",
        requires_auth=True,
        is_mutation=True,
        param_model=_MutationWithQueryParams,
    )
    await tool(name="N", ignore_duplicates=True, confirm=True)
    request = mock_hh.requests[-1]
    assert dict(request.url.params) == {}
    assert json.loads(request.read()) == {"name": "N", "ignore_duplicates": True}


class _FormBodyParams(BaseModel):
    """Модель form-операции: тело без query-полей."""

    resume_id: str | None = None
    send_sms: bool | None = None


async def test_body_format_form_sends_urlencoded(mock_hh: MockHH) -> None:
    """body_format='form': тело уходит data= (form-encoded), bool – true/false."""
    toolkit.set_client_factory(lambda: _bound_client(mock_hh))
    tool = toolkit.make_tool(
        operation_id="POST /form_demo",
        name="unit_form_post",
        summary="Form body demo",
        toolset="unit_test",
        requires_auth=True,
        is_mutation=True,
        param_model=_FormBodyParams,
        body_format="form",
    )
    await tool(resume_id="123", send_sms=True, confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert request.content == b"resume_id=123&send_sms=true"
    assert dict(request.url.params) == {}  # query-строка пуста: всё в теле.


def test_body_format_form_rejected_for_get() -> None:
    with pytest.raises(ValueError, match="POST/PUT"):
        toolkit.make_tool(
            operation_id="GET /bad_form_demo",
            name="unit_bad_form_get",
            summary="Bad form body",
            toolset="unit_test",
            requires_auth=False,
            is_mutation=False,
            param_model=_FormBodyParams,
            body_format="form",
        )


def test_query_fields_rejected_for_get() -> None:
    with pytest.raises(ValueError, match="POST/PUT"):
        toolkit.make_tool(
            operation_id="GET /bad_query_demo",
            name="unit_bad_query_get",
            summary="Bad query fields",
            toolset="unit_test",
            requires_auth=False,
            is_mutation=False,
            param_model=_MutationWithQueryParams,
            query_fields={"name"},
        )


def test_query_fields_validated_against_model() -> None:
    with pytest.raises(ValueError, match="вне модели"):
        toolkit.make_tool(
            operation_id="POST /unknown_field_demo",
            name="unit_unknown_query_field",
            summary="Unknown query field",
            toolset="unit_test",
            requires_auth=True,
            is_mutation=True,
            param_model=_MutationWithQueryParams,
            query_fields={"no_such_field"},
        )


def test_mutation_forbids_confirm_field_in_model() -> None:
    class BadModel(BaseModel):
        confirm: bool = False

    with pytest.raises(ValueError, match="confirm"):
        toolkit.make_tool(
            operation_id="POST /bad_demo",
            name="unit_bad_mutation",
            summary="Bad model",
            toolset="unit_test",
            requires_auth=True,
            is_mutation=True,
            param_model=BadModel,
        )


def test_operation_id_format_validated() -> None:
    with pytest.raises(ValueError, match="METHOD /path"):
        toolkit.make_tool(
            operation_id="demopath",
            name="unit_bad_operation",
            summary="Bad operation id",
            toolset="unit_test",
            requires_auth=False,
            is_mutation=False,
        )


# --- запрет пересечения ключей dict-body с path-параметрами (team-fix P1) ----


class _PathBodyParams(BaseModel):
    """Модель с path-параметром и dict-телом."""

    chat_id: str | None = None
    body: dict[str, Any] | None = None


async def test_body_key_clashing_with_path_param_rejected(mock_hh: MockHH) -> None:
    """Ключ body совпадает с path-параметром – HHError без HTTP-запроса."""
    toolkit.set_client_factory(lambda: _bound_client(mock_hh))
    tool = toolkit.make_tool(
        operation_id="POST /clash_demo/{chat_id}/messages",
        name="unit_clash_post",
        summary="Clash demo",
        toolset="unit_test",
        requires_auth=True,
        is_mutation=True,
        param_model=_PathBodyParams,
    )
    with pytest.raises(HHError) as excinfo:
        await tool(chat_id="5", body={"chat_id": "999", "text": "x"}, confirm=True)
    assert excinfo.value.code == "bad_request"
    assert "chat_id" in excinfo.value.description
    assert "body" in excinfo.value.description
    assert mock_hh.requests == []  # HTTP-вызов не выполнялся.


async def test_body_without_path_clash_passes(mock_hh: MockHH) -> None:
    """Обычное тело без пересечения – уходит в POST как раньше."""
    mock_hh.json_response = {"id": "1"}
    toolkit.set_client_factory(lambda: _bound_client(mock_hh))
    tool = toolkit.make_tool(
        operation_id="POST /noclash_demo/{chat_id}/messages",
        name="unit_noclash_post",
        summary="No clash demo",
        toolset="unit_test",
        requires_auth=True,
        is_mutation=True,
        param_model=_PathBodyParams,
    )
    await tool(chat_id="5", body={"text": "x"}, confirm=True)
    request = mock_hh.requests[-1]
    assert request.url.path == "/noclash_demo/5/messages"
    assert json.loads(request.read()) == {"text": "x"}
