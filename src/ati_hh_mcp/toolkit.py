"""Шаблон-декоратор инструментов: механика пишется один раз.

``make_tool`` собирает MCP-инструмент из декларативного описания:
pydantic-модель параметров превращается в плоские типизированные
параметры инструмента, мутации получают обязательный ``confirm``,
вызов направляется в ``HHClient`` по операции из реестра.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from .config import Config
from .hh.client import HHClient
from .hh.errors import HHError
from .registry import REGISTRY, ToolEntry

# Фабрика клиентов; переустанавливается при сборке сервера (и в тестах).
ClientFactory = Callable[[], HHClient]


def _default_client_factory() -> HHClient:
    return HHClient(Config.from_env())


_client_factory: ClientFactory = _default_client_factory


def set_client_factory(factory: ClientFactory) -> None:
    """Подменяет фабрику HHClient (сборка сервера, тесты)."""
    global _client_factory
    _client_factory = factory


def _parse_operation_id(operation_id: str) -> tuple[str, str]:
    """Разбирает 'GET /dictionaries' на (метод, путь)."""
    method, _, path = operation_id.partition(" ")
    method = method.upper()
    path = path.strip()
    if not path or not path.startswith("/"):
        raise ValueError(
            f"operation_id ожидается в виде 'METHOD /path', получено: {operation_id!r}"
        )
    return method, path


def make_tool(
    *,
    operation_id: str,
    name: str,
    summary: str,
    toolset: str,
    requires_auth: bool,
    is_mutation: bool,
    param_model: type[BaseModel] | None = None,
    docstring_en: str | None = None,
) -> Callable[..., Awaitable[Any]]:
    """Создаёт функцию-инструмент и регистрирует её в реестре.

    Возвращаемая функция регистрируется на сервере как ``mcp.tool(fn)``;
    параметры из ``param_model`` раскрываются на верхний уровень схемы.
    """
    method, path = _parse_operation_id(operation_id)

    if param_model is not None and is_mutation and "confirm" in param_model.model_fields:
        raise ValueError(
            f"модель параметров {param_model.__name__} не должна объявлять поле "
            "'confirm': для мутаций оно добавляется автоматически"
        )

    REGISTRY.register(
        ToolEntry(
            name=name,
            operation_id=operation_id,
            toolset=toolset,
            requires_auth=requires_auth,
            is_mutation=is_mutation,
        )
    )

    async def _run(**kwargs: Any) -> Any:
        if is_mutation and not kwargs.pop("confirm", False):
            raise HHError(
                "confirm_required",
                "Подтвердите операцию: передайте confirm=True.",
            )
        kwargs.pop("confirm", None)
        data: dict[str, Any] = {k: v for k, v in kwargs.items() if v is not None}
        client = _client_factory()
        try:
            if method == "GET":
                return await client.get(path, params=data)
            if method == "DELETE":
                return await client.delete(path, params=data)
            if method == "POST":
                return await client.post(path, json=data)
            if method == "PUT":
                return await client.put(path, json=data)
            raise ValueError(f"неподдерживаемый HTTP-метод: {method}")
        finally:
            await client.aclose()

    # Плоская сигнатура из полей модели + confirm для мутаций.
    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {"return": Any}
    if param_model is not None:
        for field_name, field in param_model.model_fields.items():
            parameters.append(
                inspect.Parameter(
                    field_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=field.default,
                    annotation=field.annotation,
                )
            )
            annotations[field_name] = field.annotation
    if is_mutation:
        parameters.append(
            inspect.Parameter(
                "confirm",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=False,
                annotation=bool,
            )
        )
        annotations["confirm"] = bool
    _run.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    _run.__annotations__ = annotations
    _run.__name__ = name
    _run.__doc__ = docstring_en or summary
    return _run
