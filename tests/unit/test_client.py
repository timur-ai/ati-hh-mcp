"""Тесты HTTP-клиента hh.ru на httpx.MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from ati_hh_mcp import __version__
from ati_hh_mcp.hh.client import CONNECT_TIMEOUT, READ_TIMEOUT, HHClient, user_agent
from ati_hh_mcp.hh.errors import HHError

from ..conftest import MockHH, make_config


def _client(mock: MockHH, **overrides: object) -> HHClient:
    return HHClient(make_config(**overrides), transport=mock.transport)  # type: ignore[arg-type]


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
