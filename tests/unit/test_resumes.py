"""Тесты набора инструментов «resumes» против MockTransport."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets import resumes

from ..conftest import MockHH, make_config

TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "get_resume": resumes.GET_RESUME,
    "get_resume_phone": resumes.GET_RESUME_PHONE,
}


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


async def test_get_resume_flags(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "r1", "title": "Python developer"}
    result = await resumes.GET_RESUME(
        resume_id="r1",
        with_negotiations_history=True,
        with_creds=True,
        with_job_search_status=True,
    )
    assert result["id"] == "r1"
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/resumes/r1"
    assert dict(request.url.params) == {
        "with_negotiations_history": "true",
        "with_creds": "true",
        "with_job_search_status": "true",
    }


async def test_get_resume_no_flags_empty_query(mock_hh: MockHH) -> None:
    await resumes.GET_RESUME(resume_id="r2")
    request = mock_hh.requests[-1]
    assert request.url.path == "/resumes/r2"
    assert dict(request.url.params) == {}


async def test_get_resume_phone_call_tracking(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"phone": "+74950000000"}
    result = await resumes.GET_RESUME_PHONE(resume_id="r1")
    assert result["phone"] == "+74950000000"
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/resumes/r1/phone"
    assert dict(request.url.params) == {}  # resume_id ушёл в путь, не в query.


def test_registry_entries_and_flags() -> None:
    entries = REGISTRY.by_toolset("resumes")
    assert sorted(e.name for e in entries) == sorted(TOOLS)
    assert len(entries) == 2
    for entry in entries:
        assert entry.requires_auth is True, entry.name
        assert entry.is_mutation is False, entry.name


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "GET /resumes/{resume_id}",
        "GET /resumes/{resume_id}/phone",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None
