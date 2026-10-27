"""Реестр соответствий «инструмент ↔ операция OpenAPI».

Единственный источник истины о составе инструментов (план, раздел
«Реестр и метатест покрытия»). Записи добавляются автоматически при
создании инструмента через ``toolkit.make_tool``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolEntry:
    """Запись реестра об одном инструменте.

    Атрибуты:
        name: имя инструмента (snake_case с доменным префиксом).
        operation_id: идентификатор операции, например ``GET /dictionaries``.
        toolset: имя набора инструментов.
        requires_auth: требуется ли токен hh.ru.
        is_mutation: изменяющая ли операция (нужен ``confirm=True``).
        undocumented: операция вне публичной OpenAPI (extended-набор).
    """

    name: str
    operation_id: str
    toolset: str
    requires_auth: bool
    is_mutation: bool
    undocumented: bool = False


class Registry:
    """Глобальное хранилище записей с поиском по имени и операции."""

    def __init__(self) -> None:
        self._by_name: dict[str, ToolEntry] = {}
        self._by_operation: dict[str, ToolEntry] = {}

    def register(self, entry: ToolEntry) -> ToolEntry:
        """Регистрирует запись; конфликт имён или операций – ошибка."""
        existing_by_name = self._by_name.get(entry.name)
        if existing_by_name is not None:
            if existing_by_name == entry:
                return entry
            raise ValueError(f"инструмент с именем {entry.name!r} уже зарегистрирован")
        if entry.operation_id in self._by_operation:
            raise ValueError(
                f"операция {entry.operation_id!r} уже занята инструментом "
                f"{self._by_operation[entry.operation_id].name!r}"
            )
        self._by_name[entry.name] = entry
        self._by_operation[entry.operation_id] = entry
        return entry

    def get(self, name: str) -> ToolEntry | None:
        """Запись по имени инструмента."""
        return self._by_name.get(name)

    def get_by_operation(self, operation_id: str) -> ToolEntry | None:
        """Запись по идентификатору операции."""
        return self._by_operation.get(operation_id)

    def all(self) -> tuple[ToolEntry, ...]:
        """Все зарегистрированные записи (в порядке регистрации)."""
        return tuple(self._by_name.values())

    def by_toolset(self, toolset: str) -> tuple[ToolEntry, ...]:
        """Записи одного набора инструментов."""
        return tuple(e for e in self._by_name.values() if e.toolset == toolset)


# Глобальный реестр проекта.
REGISTRY = Registry()
