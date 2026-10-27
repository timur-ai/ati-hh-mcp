"""Структурированные ошибки API hh.ru с русскими описаниями."""

from __future__ import annotations

from typing import Any


class HHError(Exception):
    """Ошибка обращения к API hh.ru.

    Атрибуты:
        code: машиночитаемый код ошибки (например, ``not_found``).
        description: человекочитаемое описание на русском.
        retryable: можно ли безопасно повторить запрос.
        hint: подсказка, как исправить ситуацию.
    """

    def __init__(
        self,
        code: str,
        description: str,
        *,
        retryable: bool = False,
        hint: str | None = None,
    ) -> None:
        self.code = code
        self.description = description
        self.retryable = retryable
        self.hint = hint
        super().__init__(self.__str__())

    def __str__(self) -> str:
        text = f"[{self.code}] {self.description}"
        if self.hint:
            text = f"{text} Подсказка: {self.hint}"
        return text


# Типовые коды hh.ru: статус -> (код, описание, повторяемость, подсказка).
HTTP_STATUS_MAP: dict[int, tuple[str, str, bool, str | None]] = {
    400: (
        "bad_request",
        "Некорректный запрос: hh.ru отклонил параметры (HTTP 400).",
        False,
        None,
    ),
    401: (
        "unauthorized",
        "Требуется авторизация hh.ru: запрос без действительного токена (HTTP 401).",
        False,
        "задайте токен в HH_TOKEN (stdio) или передайте заголовок X-HH-Token, "
        "либо выполните OAuth-вход",
    ),
    403: (
        "forbidden",
        "Доступ запрещён: у токена нет прав на эту операцию (HTTP 403).",
        False,
        "проверьте scope токена и роль аккаунта",
    ),
    404: (
        "not_found",
        "Объект не найден (HTTP 404).",
        False,
        "проверьте идентификатор",
    ),
    409: (
        "conflict",
        "Конфликт состояния: операция несовместима с текущим объектом (HTTP 409).",
        False,
        None,
    ),
    422: (
        "unprocessable",
        "Параметры не прошли валидацию hh.ru (HTTP 422).",
        False,
        None,
    ),
    429: (
        "rate_limited",
        "Превышен лимит запросов к hh.ru (HTTP 429).",
        True,
        "повторите запрос позже; клиент будет учитывать заголовок Retry-After",
    ),
    500: (
        "server_error",
        "Внутренняя ошибка hh.ru (HTTP 500).",
        True,
        None,
    ),
    502: (
        "bad_gateway",
        "Ошибка шлюза hh.ru (HTTP 502).",
        True,
        None,
    ),
    503: (
        "service_unavailable",
        "Сервис hh.ru временно недоступен (HTTP 503).",
        True,
        None,
    ),
    504: (
        "gateway_timeout",
        "Шлюз hh.ru не ответил вовремя (HTTP 504).",
        True,
        None,
    ),
}


def describe_error_body(body: Any) -> str | None:
    """Извлекает детали из тела ошибки hh.ru (поле ``errors``).

    Формат hh.ru: ``{"errors": [{"type": "...", "value": ...}, ...]}``,
    встречается и legacy-вариант с ``description`` внутри элементов.
    """
    if not isinstance(body, dict):
        return None
    errors = body.get("errors")
    if not isinstance(errors, list) or not errors:
        return None

    parts: list[str] = []
    for item in errors[:5]:
        if not isinstance(item, dict):
            continue
        pieces = [str(v) for v in (item.get("type"), item.get("description")) if v]
        if pieces:
            parts.append(": ".join(pieces))
    if not parts:
        return None
    suffix = "" if len(errors) <= 5 else f" (и ещё {len(errors) - 5})"
    return f"Детали: {'; '.join(parts)}{suffix}"


def error_from_response(status_code: int, body: Any) -> HHError:
    """Строит HHError из HTTP-статуса и разобранного тела ответа."""
    if status_code in HTTP_STATUS_MAP:
        code, description, retryable, hint = HTTP_STATUS_MAP[status_code]
    else:
        code = f"http_{status_code}"
        description = f"Неожиданный ответ hh.ru (HTTP {status_code})."
        retryable = False
        hint = None

    details = describe_error_body(body)
    if details:
        description = f"{description} {details}"
    return HHError(code, description, retryable=retryable, hint=hint)
