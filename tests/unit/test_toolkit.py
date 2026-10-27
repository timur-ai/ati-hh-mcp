"""Тесты реестра и шаблона инструментов (toolkit)."""

from __future__ import annotations

import inspect

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
