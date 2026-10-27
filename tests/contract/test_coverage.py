"""Контрактный метатест покрытия: инструменты ↔ операции вендорённой OpenAPI.

Инварианты (план, «Реестр и метатест покрытия»):
- каждая операция каждой группы имеет инструмент с совпадающими
  method+path (operation_id в реестре);
- для каждого реализованного инструмента (кроме служебных
  ``INTERNAL auth:*`` и всего undocumented-набора extended): обязательные
  query/path параметры операции ⊆ имена параметров инструмента
  (рекурсивно по вложенным pydantic-моделям) ⊆ множество всех параметров
  операции; служебные параметры инструмента (``confirm`` – подтверждение
  мутации, ``body`` – носитель JSON-тела POST/PUT-операций) исключены;
- нереализованные группы собраны в PENDING_TOOLSETS – тест на них не
  падает, количество оставшихся операций залогируется.

Группы покрытия объявляются файлами ``tests/contract/groups_<имя>.py``
(формат – докстринг groups_dictionaries.py) и подхватываются автоматически:
волна добавляет свой файл, метатест забирает его без правок этого модуля.
Наборы, ещё не подключённые в ``server.py`` (интеграция – lead волны),
для метатеста регистрируются на сервере напрямую.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import tempfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastmcp import Client, FastMCP

from ati_hh_mcp.config import DEFAULT_TOOLSETS
from ati_hh_mcp.hh.token_store import TokenStore
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.server import TOOLSET_MODULES, build_server
from ati_hh_mcp.toolsets import auth_tools

from ..conftest import make_config


def _ensure_auth_registered() -> None:
    """auth_tools создаёт записи реестра только внутри register().

    Для метатеста вызываем его на выброшенном сервере с in-memory store
    (регистрация идемпотентна; на инструменты боевого сервера не влияет).
    """
    throwaway = FastMCP(name="meta-auth-registration")
    auth_tools.register(throwaway, config=make_config(), store=TokenStore())


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "docs" / "openapi" / "hh-openapi.yaml"

# Временный каталог для изоляции побочных эффектов (база токенов auth).
_TEMP_DIR = Path(tempfile.mkdtemp(prefix="ati-hh-mcp-contract-"))

TOTAL_OPERATIONS = 135  # публичная OpenAPI hh.ru (фиксация ревизии спеки)


# --- автоподхват групп покрытия (tests/contract/groups_*.py) ----------------


@dataclass(frozen=True)
class GroupSpec:
    """Декларация одной группы покрытия из файла groups_*.py."""

    toolset: str
    operations: frozenset[str]  # операции вида "METHOD /path"
    requires_auth: bool
    module_name: str  # модуль набора; импорт регистрирует реестр


def _discover_groups() -> dict[str, GroupSpec]:
    """Собирает спецификации групп из всех файлов groups_*.py."""
    specs: dict[str, GroupSpec] = {}
    for mod_info in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if not mod_info.name.startswith("groups_"):
            continue
        module = importlib.import_module(f".{mod_info.name}", __package__)
        toolset: str = module.TOOLSET
        operations = frozenset(
            f"{method} {path}" for method, path in module.OPERATIONS
        )
        specs[toolset] = GroupSpec(
            toolset=toolset,
            operations=operations,
            requires_auth=bool(getattr(module, "REQUIRES_AUTH", True)),
            module_name=str(
                getattr(module, "MODULE", f"ati_hh_mcp.toolsets.{toolset}")
            ),
        )
    if not specs:
        raise RuntimeError("файлы групп покрытия groups_*.py не найдены")
    return specs


GROUPS: dict[str, GroupSpec] = _discover_groups()

# Импорт toolset-модулей регистрирует инструменты в реестре (1:1 с
# операциями групп); записи auth появляются в _ensure_auth_registered().
for _spec in GROUPS.values():
    importlib.import_module(_spec.module_name)

_ensure_auth_registered()

GROUP_OPERATIONS: dict[str, frozenset[str]] = {
    name: spec.operations for name, spec in GROUPS.items()
}
GROUP_REQUIRES_AUTH: dict[str, bool] = {
    name: spec.requires_auth for name, spec in GROUPS.items()
}
IMPLEMENTED_TOOLSETS: tuple[str, ...] = tuple(sorted(GROUPS))

# Служебные инструменты вне 135 операций: плейсхолдеры реестра вида
# "INTERNAL auth:*" (login_url/exchange_code/status) – в проверки покрытия
# не попадают (операций с такими id в спеке нет).
INTERNAL_OPERATION_PREFIX = "INTERNAL "

# Полный состав наборов проекта (план, «Группировка наборов»); группы,
# для которых файла groups_*.py ещё нет, – ожидают своей волны.
ALL_TOOLSETS: tuple[str, ...] = DEFAULT_TOOLSETS + (
    "employer_vacancies",
    "employer_negotiations",
    "employer_resumes",
    "employer_managers",
    "employer_misc",
    "extended",
)

PENDING_TOOLSETS: list[str] = sorted(
    name for name in ALL_TOOLSETS if name not in GROUPS
)

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
            # Группы, ещё не подключённые в server.py (интеграция в общий
            # словарь TOOLSET_MODULES – за lead волны): инструменты для
            # метатеста регистрируются напрямую, чтобы tools/list был полным.
            for toolset, spec in GROUPS.items():
                if toolset not in TOOLSET_MODULES:
                    module = importlib.import_module(spec.module_name)
                    module.register(server)  # type: ignore[attr-defined]
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
    """Спецификация (парсируется один раз на процесс)."""
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
    mapped = [e for e in entries if not e.operation_id.startswith(INTERNAL_OPERATION_PREFIX)]
    registered = {e.operation_id for e in mapped}
    expected = set(GROUP_OPERATIONS[toolset])
    assert registered == expected, (
        f"{toolset}: не покрыты {sorted(expected - registered)}, "
        f"лишние {sorted(registered - expected)}"
    )
    # Флаги реестра согласованы с декларацией группы и методом операции:
    # не-GET операции этого проекта – мутации с confirm.
    expected_auth = GROUP_REQUIRES_AUTH[toolset]
    for entry in mapped:
        assert entry.requires_auth is expected_auth, entry.name
        method = entry.operation_id.split(" ", 1)[0]
        assert entry.is_mutation is (method != "GET"), entry.name


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
    # Служебные параметры инструмента вне операции: confirm (подтверждение
    # мутации) и body (носитель JSON-тела POST/PUT; содержимое тела –
    # свободный словарь по схеме requestBody, в query/path не входит).
    tool_params.discard("confirm")
    tool_params.discard("body")

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
    # Дефолтные наборы волн 2–3 подключены к серверу: отклики доступны,
    # employer_* (вне DEFAULT_TOOLSETS) – скрыты.
    assert "list_negotiations" in default_names
    assert not any(name.startswith("employer_") for name in default_names)
    # extended по умолчанию скрыт, при явном включении – появляется.
    assert "apply_to_vacancy" not in default_names
    assert "apply_to_vacancy" in extended_names
    assert "my_resumes" in extended_names
