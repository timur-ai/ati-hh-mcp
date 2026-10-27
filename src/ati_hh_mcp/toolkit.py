"""Шаблон-декоратор инструментов: механика пишется один раз.

``make_tool`` собирает MCP-инструмент из декларативного описания:
pydantic-модель параметров превращается в плоские типизированные
параметры инструмента, мутации получают обязательный ``confirm``,
вызов направляется в ``HHClient`` по операции из реестра.

Path-параметры операции (``/vacancies/{vacancy_id}``) подставляются в путь
и исключаются из query; значения-модели (двухуровневая схема тяжёлых
операций) разворачиваются в плоские query-параметры.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from urllib.parse import quote

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


def flatten_params(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Разворачивает значения-модели в плоские параметры запроса.

    Вложенные pydantic-модели (двухуровневая схема) превращаются в их поля
    (только заданные); None-значения верхнего уровня отбрасываются.
    Словарь обрабатывается так же, как модель (защита от сырых значений).
    """
    flat: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, BaseModel):
            flat.update(value.model_dump(exclude_none=True))
        elif isinstance(value, dict):
            flat.update({k: v for k, v in value.items() if v is not None})
        else:
            flat[key] = value
    return flat


def render_path(path: str, params: dict[str, Any]) -> str:
    """Подставляет path-параметры в шаблон пути, изымая их из params.

    ``render_path('/v/{id}', {'id': 42}) -> '/v/42'``; значения кодируются
    для URL. Словарь params изменяется на месте (параметры изымаются).
    """
    rendered = path
    for name in re.findall(r"\{(\w+)\}", path):
        if name not in params:
            raise ValueError(
                f"для пути {path!r} не передан path-параметр {name!r}"
            )
        rendered = rendered.replace("{" + name + "}", quote(str(params.pop(name)), safe=""))
    return rendered


def _split_query_body(
    data: dict[str, Any],
    query_fields: frozenset[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Делит параметры POST/PUT на query-часть и тело запроса."""
    if not query_fields:
        return {}, data
    query = {k: v for k, v in data.items() if k in query_fields}
    body = {k: v for k, v in data.items() if k not in query_fields}
    return query, body


def _form_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Значения для x-www-form-urlencoded-тела.

    ``bool`` приводится к строкам ``true``/``false`` (стиль JSON): httpx
    кодирует примитивы формы через ``str()`` и превратил бы ``True`` в
    ``"True"``, которое API hh.ru не разбирает.
    """
    return {
        key: str(value).lower() if isinstance(value, bool) else value
        for key, value in data.items()
    }


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
    query_fields: frozenset[str] | set[str] | None = None,
    body_format: Literal["json", "form"] = "json",
) -> Callable[..., Awaitable[Any]]:
    """Создаёт функцию-инструмент и регистрирует её в реестре.

    Возвращаемая функция регистрируется на сервере как ``mcp.tool(fn)``;
    параметры из ``param_model`` раскрываются на верхний уровень схемы.

    ``query_fields`` – имена полей ``param_model``, которые для POST/PUT
    уходят в query-строку, а не в тело (мутации hh.ru с query-параметрами:
    ``ignore_duplicates`` у POST /vacancies, ``successor_id`` у DELETE
    менеджеров и т.п.). Для GET/DELETE недопустим (там всё и так query).

    ``body_format`` – кодировка тела POST/PUT: ``"json"`` (по умолчанию)
    или ``"form"`` (``application/x-www-form-urlencoded`` через ``data=``;
    для операций, у которых вендор-спека декларирует form-тело:
    preferred_negotiations_order, phone_interview, applicant_comments).
    Для GET/DELETE недопустим (тела нет).
    """
    method, path = _parse_operation_id(operation_id)

    if param_model is not None and is_mutation and "confirm" in param_model.model_fields:
        raise ValueError(
            f"модель параметров {param_model.__name__} не должна объявлять поле "
            "'confirm': для мутаций оно добавляется автоматически"
        )

    if body_format not in ("json", "form"):
        raise ValueError(f"body_format ожидает 'json' или 'form', получено: {body_format!r}")
    if body_format == "form" and method not in ("POST", "PUT"):
        raise ValueError(
            f"body_format='form' применим только к POST/PUT; {method} не "
            "отправляет тело запроса"
        )

    effective_query_fields = frozenset(query_fields) if query_fields else frozenset()
    if effective_query_fields:
        if method not in ("POST", "PUT"):
            raise ValueError(
                f"query_fields применим только к POST/PUT; {method} и так "
                "отправляет все параметры в query-строку"
            )
        if param_model is not None:
            unknown = effective_query_fields - set(param_model.model_fields)
            if unknown:
                raise ValueError(
                    f"query_fields содержит поля вне модели {param_model.__name__}: "
                    f"{sorted(unknown)}"
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
        # Ключи dict-body не должны совпадать с path-параметрами операции:
        # после разворачивания такой ключ затёрл бы значение пути.
        raw_body = kwargs.get("body")
        if isinstance(raw_body, dict):
            path_params = set(re.findall(r"\{(\w+)\}", path))
            clash = sorted(path_params & raw_body.keys())
            if clash:
                raise HHError(
                    "bad_request",
                    "Ключ(и) body "
                    + ", ".join(repr(k) for k in clash)
                    + " конфликтуют с path-параметром операции; уберите их из body.",
                )
        data = flatten_params(kwargs)
        request_path = render_path(path, data)
        client = _client_factory()
        try:
            if method == "GET":
                return await client.get(request_path, params=data)
            if method == "DELETE":
                return await client.delete(request_path, params=data)
            if method in ("POST", "PUT"):
                query, body = _split_query_body(data, effective_query_fields)
                sender = client.post if method == "POST" else client.put
                if body_format == "form":
                    return await sender(
                        request_path, params=query, data=_form_fields(body) or None
                    )
                return await sender(request_path, params=query, json=body or None)
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
                    default=inspect.Parameter.empty
                    if field.is_required()
                    else field.default,
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
