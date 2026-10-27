"""Контрактный метатест покрытия: инструменты ↔ операции вендорённой OpenAPI.

Инварианты (план, «Реестр и метатест покрытия»):
- каждая операция групп dictionaries/suggests/vacancies/auth имеет
  инструмент с совпадающими method+path (operation_id в реестре);
- для каждого реализованного инструмента (кроме служебных
  ``INTERNAL auth:*`` и всего undocumented-набора extended): обязательные
  query/path параметры операции ⊆ имена параметров инструмента
  (рекурсивно по вложенным pydantic-моделям; служебный confirm исключён)
  ⊆ множество всех параметров операции;
- нереализованные группы собраны в PENDING_TOOLSETS (волны 3) – тест на
  них не падает, количество оставшихся операций залогируется.
"""

from __future__ import annotations

import os
import tempfile
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastmcp import Client, FastMCP

from ati_hh_mcp.config import DEFAULT_TOOLSETS
from ati_hh_mcp.hh.token_store import TokenStore
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.server import build_server

# Импорт toolset-модулей регистрирует инструменты в реестре (1:1 с операциями).
from ati_hh_mcp.toolsets import (
    auth_tools,
    dictionaries,  # noqa: F401
    extended,  # noqa: F401
    suggests,  # noqa: F401
    vacancies,  # noqa: F401
)

from ..conftest import make_config


def _ensure_auth_registered() -> None:
    """auth_tools создаёт записи реестра только внутри register().

    Для метатеста вызываем его на выброшенном сервере с in-memory store
    (регистрация идемпотентна; на инструменты боевого сервера не влияет).
    """
    throwaway = FastMCP(name="meta-auth-registration")
    auth_tools.register(throwaway, config=make_config(), store=TokenStore())


_ensure_auth_registered()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "docs" / "openapi" / "hh-openapi.yaml"

# Временный каталог для изоляции побочных эффектов (база токенов auth).
_TEMP_DIR = Path(tempfile.mkdtemp(prefix="ati-hh-mcp-contract-"))

TOTAL_OPERATIONS = 135  # публичная OpenAPI hh.ru (фиксация ревизии спеки)

# Группы, отображаемые на операции спеки: волна 2 (M3a) + auth (M5-модули).
IMPLEMENTED_TOOLSETS = ("dictionaries", "suggests", "vacancies", "auth")

# Служебные инструменты вне 135 операций: плейсхолдеры реестра вида
# "INTERNAL auth:*" (login_url/exchange_code/status) – в проверки покрытия
# не попадают (операций с такими id в спеке нет).
INTERNAL_OPERATION_PREFIX = "INTERNAL "

GROUP_OPERATIONS: dict[str, frozenset[str]] = {
    "dictionaries": frozenset(
        {
            "GET /dictionaries",
            "GET /areas",
            "GET /areas/countries",
            "GET /areas/{area_id}",
            "GET /industries",
            "GET /professional_roles",
            "GET /languages",
            "GET /locales",
            "GET /locales/resume",
            "GET /districts",
            "GET /metro",
            "GET /metro/{city_id}",
            "GET /skills",
            "GET /educational_institutions",
            "GET /educational_institutions/{id}/faculties",
            "GET /vacancy_conditions",
        }
    ),
    "suggests": frozenset(
        {
            "GET /suggests/areas",
            "GET /suggests/area_leaves",
            "GET /suggests/companies",
            "GET /suggests/educational_institutions",
            "GET /suggests/fields_of_study",
            "GET /suggests/positions",
            "GET /suggests/professional_roles",
            "GET /suggests/resume_search_keyword",
            "GET /suggests/skill_set",
            "GET /suggests/vacancy_positions",
            "GET /suggests/vacancy_search_keyword",
        }
    ),
    "vacancies": frozenset(
        {
            "GET /vacancies",
            "GET /vacancies/{vacancy_id}",
            "GET /vacancies/{vacancy_id}/similar_vacancies",
            "GET /vacancies/{vacancy_id}/related_vacancies",
        }
    ),
    # auth: операции из 135, покрытые инструментами; auth_get_login_url/
    # auth_exchange_code/auth_status – служебные (INTERNAL auth:*), вне 135.
    "auth": frozenset(
        {
            "GET /me",
            "DELETE /token",
        }
    ),
}

# Группы следующих волн (волны 3, M3b–M3d) и undocumented-набор extended
# (M6; его операции вне публичной спеки). Список должен уменьшаться по мере
# реализации; тест на них не падает.
PENDING_TOOLSETS = [
    "negotiations",
    "chats",
    "resumes",
    "employer_vacancies",
    "employer_negotiations",
    "employer_resumes",
    "employer_managers",
    "employer_misc",
    "extended",
]

# Операции без отдельного инструмента по решению реестра.
INTERNAL_OPERATIONS = {
    "POST /token": "internal: обмен OAuth-кода внутри hh/auth.py (M5)",
}

# Служебные параметры спецификации, управляемые клиентом (не инструментом).
SERVICE_PARAM_NAMES = frozenset({"Host", "Locale", "HHUserAgent"})

IMPLEMENTED_OPERATIONS: frozenset[str] = frozenset().union(*GROUP_OPERATIONS.values())


@cache
def _load_spec() -> dict[str, Any]:
    with SPEC_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _spec_operations(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Все операции спеки: 'METHOD /path' -> объект операции."""
    operations: dict[str, dict[str, Any]] = {}
    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if method in ("get", "post", "put", "delete", "patch"):
                operations[f"{method.upper()} {path}"] = op
    return operations


def _operation_params(
    op: dict[str, Any], spec: dict[str, Any]
) -> tuple[set[str], set[str]]:
    """(обязательные, все) query/path-параметры операции без служебных."""
    required: set[str] = set()
    all_names: set[str] = set()
    for param in op.get("parameters", []):
        if "$ref" in param:
            ref_name = param["$ref"].split("/")[-1]
            param = spec.get("components", {}).get("parameters", {}).get(ref_name, {})
        if param.get("name") in SERVICE_PARAM_NAMES:
            continue  # Host/Locale/HHUserAgent задаёт сам клиент.
        if param.get("in") not in ("query", "path"):
            continue
        all_names.add(str(param["name"]))
        if param.get("required"):
            required.add(str(param["name"]))
    return required, all_names


def _resolve_ref(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        ref_name = str(node["$ref"]).split("/")[-1]
        return defs.get(ref_name, {})
    return node


def _object_schema(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any] | None:
    """Развёрнутая object-схема узла (напрямую, через $ref или anyOf)."""
    resolved = _resolve_ref(node, defs)
    if resolved.get("type") == "object" and "properties" in resolved:
        return resolved
    for key in ("anyOf", "oneOf"):
        for variant in node.get(key, []):
            resolved_variant = _resolve_ref(variant, defs)
            if resolved_variant.get("type") == "object" and "properties" in resolved_variant:
                return resolved_variant
    return None


def _schema_leaf_names(schema: dict[str, Any], defs: dict[str, Any]) -> set[str]:
    """Имена параметров-листьев; вложенные object-контейнеры рекурсивно
    раскрываются (двухуровневая схема advanced)."""
    names: set[str] = set()
    for prop_name, prop in schema.get("properties", {}).items():
        nested = _object_schema(prop, defs)
        if nested is not None:
            names |= _schema_leaf_names(nested, defs)
        else:
            names.add(prop_name)
    return names


_schema_cache: dict[str, dict[str, Any]] | None = None


async def _tool_input_schemas() -> dict[str, dict[str, Any]]:
    """Реальные схемы инструментов через in-memory MCP-клиент (не заглушка)."""
    global _schema_cache
    if _schema_cache is None:
        # Хранилище токенов auth-набора – во временный каталог, не в HOME.
        store_env = os.environ.get("HH_TOKEN_STORE")
        os.environ["HH_TOKEN_STORE"] = str(_TEMP_DIR / "tokens.sqlite3")
        try:
            server = build_server(make_config(toolsets=IMPLEMENTED_TOOLSETS))
            async with Client(server) as client:
                tools = await client.list_tools()
        finally:
            if store_env is None:
                os.environ.pop("HH_TOKEN_STORE", None)
            else:
                os.environ["HH_TOKEN_STORE"] = store_env
        _schema_cache = {tool.name: dict(tool.input_schema) for tool in tools}
    return _schema_cache


def _spec() -> dict[str, Any]:
    """Спецификация (парсится один раз на процесс)."""
    return _load_spec()


def test_vendored_spec_present_with_expected_operations() -> None:
    assert SPEC_PATH.exists(), "вендорённая спецификация отсутствует"
    operations = _spec_operations(_spec())
    assert len(operations) == TOTAL_OPERATIONS


@pytest.mark.parametrize("toolset", IMPLEMENTED_TOOLSETS)
def test_group_operations_have_registry_tools(toolset: str) -> None:
    """Каждая операция группы покрыта инструментом с теми же method+path."""
    entries = REGISTRY.by_toolset(toolset)
    # Служебные INTERNAL auth:* не отображаются на операции спеки.
    registered = {
        e.operation_id
        for e in entries
        if not e.operation_id.startswith(INTERNAL_OPERATION_PREFIX)
    }
    expected = set(GROUP_OPERATIONS[toolset])
    assert registered == expected, (
        f"{toolset}: не покрыты {sorted(expected - registered)}, "
        f"лишние {sorted(registered - expected)}"
    )
    if toolset in ("dictionaries", "suggests", "vacancies"):
        for entry in entries:
            assert entry.requires_auth is False, entry.name
            assert entry.is_mutation is False, entry.name
    else:  # auth: флаги по решению реестра
        assert REGISTRY.get("get_me").requires_auth is True  # type: ignore[union-attr]
        assert REGISTRY.get("get_me").is_mutation is False  # type: ignore[union-attr]
        assert REGISTRY.get("auth_logout").is_mutation is True  # type: ignore[union-attr]


IMPLEMENTED_TOOLS = sorted(
    entry.name
    for toolset in IMPLEMENTED_TOOLSETS
    for entry in REGISTRY.by_toolset(toolset)
    if not entry.operation_id.startswith(INTERNAL_OPERATION_PREFIX)
)


@pytest.mark.parametrize("tool_name", IMPLEMENTED_TOOLS)
async def test_parametric_contract(tool_name: str) -> None:
    """обязательные ⊆ параметры инструмента ⊆ параметры операции."""
    entry = REGISTRY.get(tool_name)
    assert entry is not None, tool_name

    spec = _spec()
    operations = _spec_operations(spec)
    op = operations.get(entry.operation_id)
    assert op is not None, f"{entry.operation_id} отсутствует в спецификации"

    schemas = await _tool_input_schemas()
    schema = schemas[tool_name]
    tool_params = _schema_leaf_names(schema, schema.get("$defs", {}))
    # Служебный параметр подтверждения мутаций в контракт не входит.
    tool_params.discard("confirm")

    required, all_names = _operation_params(op, spec)
    missing = required - tool_params
    assert not missing, (
        f"{tool_name}: обязательные параметры операции не объявлены: {sorted(missing)}"
    )
    extra = tool_params - all_names
    assert not extra, (
        f"{tool_name}: параметры вне операции {entry.operation_id}: {sorted(extra)}"
    )


def test_coverage_accounting_and_pending_logged() -> None:
    """implemented + internal + pending = все операции; pending залогирован."""
    spec = _spec()
    operations = set(_spec_operations(spec))
    registered = {
        e.operation_id
        for e in REGISTRY.all()
        if e.toolset in IMPLEMENTED_TOOLSETS
        and not e.operation_id.startswith(INTERNAL_OPERATION_PREFIX)
    }
    internal = set(INTERNAL_OPERATIONS)
    pending = operations - registered - internal

    implemented = operations & registered
    assert implemented == IMPLEMENTED_OPERATIONS, "реестр и группы расходятся"

    # Ни одна операция реализованной группы не осталась в pending.
    assert not pending & IMPLEMENTED_OPERATIONS

    # Журнал: количество оставшихся операций должно уменьшаться волнами.
    print(
        f"\n[pending] операций вне реализованных групп: {len(pending)} из "
        f"{len(operations)} (PENDING_TOOLSETS={PENDING_TOOLSETS})"
    )
    assert len(operations) == TOTAL_OPERATIONS


async def test_default_toolsets_hide_extended_and_show_auth() -> None:
    """По умолчанию auth есть в tools/list, extended – нет; с extended – есть."""
    store_env = os.environ.get("HH_TOKEN_STORE")
    os.environ["HH_TOKEN_STORE"] = str(_TEMP_DIR / "default.sqlite3")
    try:
        default_server = build_server(make_config(toolsets=DEFAULT_TOOLSETS))
        extended_server = build_server(
            make_config(toolsets=DEFAULT_TOOLSETS + ("extended",))
        )
        async with Client(default_server) as client:
            default_names = {tool.name for tool in await client.list_tools()}
        async with Client(extended_server) as client:
            extended_names = {tool.name for tool in await client.list_tools()}
    finally:
        if store_env is None:
            os.environ.pop("HH_TOKEN_STORE", None)
        else:
            os.environ["HH_TOKEN_STORE"] = store_env

    # auth-инструменты доступны всегда (набор в дефолтной конфигурации).
    assert {"auth_status", "get_me", "auth_get_login_url"} <= default_names
    # extended по умолчанию скрыт, при явном включении – появляется.
    assert "apply_to_vacancy" not in default_names
    assert "apply_to_vacancy" in extended_names
    assert "my_resumes" in extended_names
    # Нереализованные наборы (волны 3) молча пропускаются.
    assert not any(name.startswith("list_negotiations") for name in default_names)
