"""Тесты HTTP-клиента hh.ru на httpx.MockTransport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from ati_hh_mcp import __version__
from ati_hh_mcp.hh.client import (
    CONNECT_TIMEOUT,
    GET_RETRY_BACKOFFS,
    READ_TIMEOUT,
    HHAuthExpiredError,
    HHClient,
    user_agent,
)
from ati_hh_mcp.hh.errors import HHError

from ..conftest import MockHH, make_config


def _client(mock: MockHH, **overrides: object) -> HHClient:
    return HHClient(make_config(**overrides), transport=mock.transport)  # type: ignore[arg-type]


class _ScriptedTransport(httpx.MockTransport):
    """Транспорт, раздающий заготовленные ответы по порядку."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self.responses.pop(0)

        super().__init__(handler)


class _Recorder:
    """Заменитель asyncio.sleep: фиксирует паузы повторов."""

    def __init__(self) -> None:
        self.pauses: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.pauses.append(seconds)


async def test_user_agent_header_format() -> None:
    assert user_agent("owner@example.test") == f"ati-hh-mcp/{__version__} (owner@example.test)"


async def test_headers_with_token(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"ok": True}
    async with _client(mock_hh, token="secret-token") as client:
        await client.get("/me")
    request = mock_hh.requests[0]
    assert request.headers["User-Agent"] == f"ati-hh-mcp/{__version__} (owner@example.test)"
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert request.headers["Accept"] == "application/json"


async def test_no_authorization_header_without_token(mock_hh: MockHH) -> None:
    async with _client(mock_hh) as client:
        await client.get("/dictionaries")
    assert "Authorization" not in mock_hh.requests[0].headers


async def test_get_path_and_params(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    async with _client(mock_hh) as client:
        result = await client.get("/vacancies", params={"text": "python", "page": 2})
    request = mock_hh.requests[0]
    assert request.method == "GET"
    assert request.url.path == "/vacancies"
    assert request.url.params["text"] == "python"
    assert request.url.params["page"] == "2"
    assert result == {"items": []}


async def test_post_json_body(mock_hh: MockHH) -> None:
    async with _client(mock_hh) as client:
        await client.post("/negotiations", json={"vacancy_id": 1})
    request = mock_hh.requests[0]
    assert request.method == "POST"
    assert json.loads(request.read()) == {"vacancy_id": 1}


async def test_base_url_applied(mock_hh: MockHH) -> None:
    async with _client(mock_hh) as client:
        assert client.base_url == "https://api.hh.test"
        await client.get("/dictionaries")
    assert mock_hh.requests[0].url.host == "api.hh.test"


async def test_timeouts_configured(mock_hh: MockHH) -> None:
    async with _client(mock_hh) as client:
        timeout = client._client.timeout
        assert timeout.connect == CONNECT_TIMEOUT == 10.0
        assert timeout.read == READ_TIMEOUT == 30.0


@pytest.mark.parametrize(
    ("status", "code", "retryable", "description_part"),
    [
        (400, "bad_request", False, "Некорректный запрос"),
        (404, "not_found", False, "не найден"),
        (429, "rate_limited", True, "лимит запросов"),
    ],
)
async def test_error_mapping(
    mock_hh: MockHH,
    status: int,
    code: str,
    retryable: bool,
    description_part: str,
) -> None:
    mock_hh.status_code = status
    mock_hh.json_response = {"errors": [{"type": "demo-error", "value": "x"}]}
    async with _client(mock_hh) as client:
        with pytest.raises(HHError) as excinfo:
            await client.get("/vacancies")
    error = excinfo.value
    assert error.code == code
    assert error.retryable is retryable
    assert description_part in error.description
    # Детали из тела errors hh.ru добавлены к описанию.
    assert "demo-error" in error.description


async def test_unauthorized_error_hint(mock_hh: MockHH) -> None:
    mock_hh.status_code = 401
    async with _client(mock_hh) as client:
        with pytest.raises(HHError) as excinfo:
            await client.get("/me")
    assert excinfo.value.code == "unauthorized"
    assert excinfo.value.hint is not None
    assert "HH_TOKEN" in excinfo.value.hint


async def test_unexpected_status_code(mock_hh: MockHH) -> None:
    mock_hh.status_code = 418
    async with _client(mock_hh) as client:
        with pytest.raises(HHError) as excinfo:
            await client.get("/vacancies")
    assert excinfo.value.code == "http_418"


async def test_non_json_error_body(mock_hh: MockHH) -> None:
    mock_hh.status_code = 502
    broken = httpx.MockTransport(
        lambda request: httpx.Response(502, content=b"bad gateway")
    )
    client = HHClient(make_config(), transport=broken)
    with pytest.raises(HHError) as excinfo:
        await client.get("/vacancies")
    assert excinfo.value.code == "bad_gateway"
    assert excinfo.value.retryable is True


async def test_put_and_delete(mock_hh: MockHH) -> None:
    async with _client(mock_hh) as client:
        await client.put("/negotiations/5", json={"state": "response"})
        await client.delete("/token")
    methods = [r.method for r in mock_hh.requests]
    assert methods == ["PUT", "DELETE"]


# --- Повторы (только GET + 429) -------------------------------------------


async def test_get_429_retries_with_backoff_and_succeeds() -> None:
    transport = _ScriptedTransport(
        [
            httpx.Response(429, json={"errors": []}),
            httpx.Response(429, json={"errors": []}),
            httpx.Response(200, json={"items": ["ok"]}),
        ]
    )
    sleep = _Recorder()
    client = HHClient(make_config(), transport=transport, sleep=sleep)
    result = await client.get("/vacancies")
    assert result == {"items": ["ok"]}
    assert len(transport.requests) == 3
    # Два повтора по фолбэк-паузам 0.5 и 1.0 (Retry-After отсутствует).
    assert sleep.pauses == [GET_RETRY_BACKOFFS[0], GET_RETRY_BACKOFFS[1]]


async def test_get_429_honors_retry_after_header() -> None:
    transport = _ScriptedTransport(
        [
            httpx.Response(429, headers={"Retry-After": "3"}, json={}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sleep = _Recorder()
    client = HHClient(make_config(), transport=transport, sleep=sleep)
    await client.get("/vacancies")
    assert sleep.pauses == [3.0]


async def test_get_429_gives_up_after_three_retries() -> None:
    transport = _ScriptedTransport(
        [httpx.Response(429, json={}) for _ in range(1 + len(GET_RETRY_BACKOFFS))]
    )
    sleep = _Recorder()
    client = HHClient(make_config(), transport=transport, sleep=sleep)
    with pytest.raises(HHError) as excinfo:
        await client.get("/vacancies")
    assert excinfo.value.code == "rate_limited"
    assert excinfo.value.retryable is True
    # Ровно 4 попытки (исходная + 3 повтора), паузы 0.5/1/2.
    assert len(transport.requests) == 4
    assert sleep.pauses == list(GET_RETRY_BACKOFFS)


async def test_post_429_is_never_retried() -> None:
    transport = _ScriptedTransport([httpx.Response(429, json={})])
    sleep = _Recorder()
    client = HHClient(make_config(), transport=transport, sleep=sleep)
    with pytest.raises(HHError) as excinfo:
        await client.post("/negotiations", json={"vacancy_id": 1})
    assert excinfo.value.code == "rate_limited"
    assert len(transport.requests) == 1
    assert sleep.pauses == []


async def test_put_delete_429_not_retried() -> None:
    for method_call in ("put", "delete"):
        transport = _ScriptedTransport([httpx.Response(429, json={})])
        sleep = _Recorder()
        client = HHClient(make_config(), transport=transport, sleep=sleep)
        with pytest.raises(HHError):
            if method_call == "put":
                await client.put("/negotiations/1", json={"state": "response"})
            else:
                await client.delete("/token")
        assert len(transport.requests) == 1, method_call
        assert sleep.pauses == [], method_call


# --- Таймауты и сетевые сбои ----------------------------------------------


async def test_get_timeout_maps_to_hherror() -> None:
    def raiser(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no answer")

    client = HHClient(make_config(), transport=httpx.MockTransport(raiser))
    with pytest.raises(HHError) as excinfo:
        await client.get("/vacancies")
    assert excinfo.value.code == "timeout"
    # GET безопасно повторять вручную.
    assert excinfo.value.retryable is True


async def test_post_timeout_is_not_retryable_and_warns() -> None:
    def raiser(request: httpx.Request) -> httpx.Response:
        raise httpx.WriteTimeout("cut off")

    sleep = _Recorder()
    client = HHClient(
        make_config(), transport=httpx.MockTransport(raiser), sleep=sleep
    )
    with pytest.raises(HHError) as excinfo:
        await client.post("/negotiations", json={"vacancy_id": 1})
    assert excinfo.value.code == "timeout"
    assert excinfo.value.retryable is False
    assert excinfo.value.hint is not None
    assert "могла не выполниться" in excinfo.value.hint
    assert sleep.pauses == []  # никаких автоповторов у мутаций.


async def test_delete_network_error_not_retryable() -> None:
    def raiser(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = HHClient(make_config(), transport=httpx.MockTransport(raiser))
    with pytest.raises(HHError) as excinfo:
        await client.delete("/token")
    assert excinfo.value.code == "network_error"
    assert excinfo.value.retryable is False
    assert excinfo.value.hint is not None
    assert "перед повтором" in excinfo.value.hint


# --- 401: подтип auth_expired ---------------------------------------------


async def test_401_raises_auth_expired_error() -> None:
    mock_hh = MockHH(status_code=401, json_response={"errors": []})
    async with _client(mock_hh, token="expired") as client:
        with pytest.raises(HHAuthExpiredError) as excinfo:
            await client.get("/me")
    error = excinfo.value
    assert error.auth_expired is True
    assert isinstance(error, HHError)  # подтип остаётся совместимым с базой.
    assert error.code == "unauthorized"
    assert "HH_TOKEN" in (error.hint or "")


async def test_401_auth_expired_for_post_too() -> None:
    transport = _ScriptedTransport([httpx.Response(401, json={})])
    client = HHClient(make_config(), transport=transport)
    with pytest.raises(HHAuthExpiredError):
        await client.post("/artifacts", json={"name": "x"})


# --- Пагинация: параметры и служебные поля проходят насквозь ---------------


async def test_pagination_params_and_fields_passthrough(mock_hh: MockHH) -> None:
    payload: dict[str, Any] = {
        "items": [{"id": "1"}],
        "page": 1,
        "per_page": 1,
        "pages": 99,
        "found": 1234,
        "clusters": [{"id": "area", "items": []}],
    }
    mock_hh.json_response = payload
    async with _client(mock_hh) as client:
        result = await client.get("/vacancies", params={"text": "python", "page": 1, "per_page": 1})
    request = mock_hh.requests[0]
    # Параметры пагинации не фильтруются клиентом.
    assert request.url.params["page"] == "1"
    assert request.url.params["per_page"] == "1"
    assert request.url.params["text"] == "python"
    # Служебные поля ответа (found/pages/clusters) проходят без изменений.
    assert result == payload


# --- Form-тело и multipart -------------------------------------------------


async def test_post_form_encoded_body() -> None:
    mock_hh = MockHH(json_response={"access_token": "AT"})
    async with _client(mock_hh) as client:
        result = await client.post("/token", data={"grant_type": "refresh_token"})
    assert result == {"access_token": "AT"}
    request = mock_hh.requests[0]
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert "grant_type=refresh_token" in request.read().decode()


async def test_put_form_encoded_body() -> None:
    mock_hh = MockHH(json_response={"ok": True})
    async with _client(mock_hh) as client:
        await client.put("/settings", data={"locale": "RU"})
    request = mock_hh.requests[0]
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert "locale=RU" in request.read().decode()


async def test_post_multipart_returns_raw_response() -> None:
    transport = _ScriptedTransport(
        [httpx.Response(201, headers={"Location": "/negotiations/9"})]
    )
    client = HHClient(make_config(), transport=transport)
    response = await client.post_multipart(
        "/negotiations", fields={"vacancy_id": "V1", "resume_id": "R1", "message": "Привет"}
    )
    # Сырой ответ: статус и заголовки доступны вызывающему.
    assert response.status_code == 201
    assert response.headers["Location"] == "/negotiations/9"

    request = transport.requests[0]
    assert request.method == "POST"
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert b"vacancy_id" in body and b"V1" in body
    assert b"resume_id" in body and b"R1" in body
    assert "Привет".encode() in body


async def test_post_multipart_error_maps_to_hherror() -> None:
    transport = _ScriptedTransport([httpx.Response(409, json={"errors": []})])
    client = HHClient(make_config(), transport=transport)
    with pytest.raises(HHError) as excinfo:
        await client.post_multipart("/negotiations", fields={"vacancy_id": "V1"})
    assert excinfo.value.code == "conflict"
    assert len(transport.requests) == 1  # мутация не повторяется.
