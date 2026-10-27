"""Набор «dictionaries»: справочники hh.ru.

Три инструмента вертикального среза (M1); полный набор справочников
(areas по id, professional_roles, languages и др.) – этап M3a.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP

from ..toolkit import make_tool

DICT_DICTIONARIES = make_tool(
    operation_id="GET /dictionaries",
    name="dict_dictionaries",
    summary="Get hh.ru core dictionaries",
    toolset="dictionaries",
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get hh.ru core dictionaries: currencies, genders, vacancies statuses "
        "and other enumerations used across the API."
    ),
)

DICT_AREAS = make_tool(
    operation_id="GET /areas",
    name="dict_areas",
    summary="Get the hh.ru regions tree",
    toolset="dictionaries",
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get the full tree of hh.ru regions (areas): countries, federal "
        "subjects and cities, with their numeric ids."
    ),
)

DICT_METRO = make_tool(
    operation_id="GET /metro",
    name="dict_metro",
    summary="Get hh.ru metro lines and stations",
    toolset="dictionaries",
    requires_auth=False,
    is_mutation=False,
    docstring_en=(
        "Get metro lines and stations for all hh.ru cities that have a metro "
        "map, grouped by city with station ids."
    ),
)

_TOOLS: tuple[Callable[..., Awaitable[Any]], ...] = (DICT_DICTIONARIES, DICT_AREAS, DICT_METRO)


def register(mcp: FastMCP) -> None:
    """Подключает все инструменты набора к серверу."""
    for tool in _TOOLS:
        mcp.tool(tool)
