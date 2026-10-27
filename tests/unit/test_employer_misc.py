"""Тесты набора инструментов «employer_misc» против MockTransport."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets.employer_misc import (
    DICT_SALARY_AREAS,
    DICT_SALARY_EMPLOYEE_LEVELS,
    DICT_SALARY_INDUSTRIES,
    DICT_SALARY_PROFESSIONAL_AREAS,
    EMPLOYER_CREATE_WEBHOOK_SUBSCRIPTION,
    EMPLOYER_DELETE_WEBHOOK_SUBSCRIPTION,
    EMPLOYER_GET_ADDRESS,
    EMPLOYER_GET_CALL_HISTORY,
    EMPLOYER_GET_CALL_LINK,
    EMPLOYER_GET_CLICKME_STATISTICS,
    EMPLOYER_GET_SALARY_EVALUATION,
    EMPLOYER_LIST_ACTIVE_VACANCY_AREAS,
    EMPLOYER_LIST_ADDRESSES,
    EMPLOYER_LIST_AVAILABLE_PUBLICATIONS,
    EMPLOYER_LIST_DEPARTMENTS,
    EMPLOYER_LIST_PAYABLE_API_ACTIONS,
    EMPLOYER_LIST_TESTS,
    EMPLOYER_LIST_VACANCY_BRANDED_TEMPLATES,
    EMPLOYER_LIST_WEBHOOK_SUBSCRIPTIONS,
    EMPLOYER_SEARCH_CALL_RECORDS,
    EMPLOYER_SEARCH_CALL_TRANSCRIPTS,
    EMPLOYER_UPDATE_WEBHOOK_SUBSCRIPTION,
    GET_EMPLOYER,
    GET_MESSAGE_TEMPLATE,
    SEARCH_EMPLOYERS,
)

from ..conftest import MockHH, make_config

PUBLIC_TOOLS = frozenset(
    {
        "search_employers",
        "get_employer",
        "dict_salary_industries",
        "dict_salary_professional_areas",
        "dict_salary_employee_levels",
        "dict_salary_areas",
    }
)

MUTATIONS = frozenset(
    {
        "employer_create_webhook_subscription",
        "employer_update_webhook_subscription",
        "employer_delete_webhook_subscription",
    }
)


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


# --- публичные: работодатели и справочники зарплатной статистики -----------


async def test_search_employers_query(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": [], "found": 1, "page": 0, "pages": 1}
    result = await SEARCH_EMPLOYERS(
        text="Витте",
        area="1",
        type="company",
        only_with_vacancies=True,
        sort_by="by_vacancies_open",
        page=0,
        per_page=50,
    )
    assert result["found"] == 1
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/employers"
    assert dict(request.url.params) == {
        "text": "Витте",
        "area": "1",
        "type": "company",
        "only_with_vacancies": "true",
        "sort_by": "by_vacancies_open",
        "page": "0",
        "per_page": "50",
    }


async def test_get_employer_path(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "1455", "name": "Витте Консалтинг"}
    result = await GET_EMPLOYER(employer_id="1455")
    assert result["id"] == "1455"
    request = mock_hh.requests[-1]
    assert request.url.path == "/employers/1455"
    assert dict(request.url.params) == {}


async def test_salary_dictionaries_no_params(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await DICT_SALARY_INDUSTRIES()
    await DICT_SALARY_PROFESSIONAL_AREAS()
    await DICT_SALARY_EMPLOYEE_LEVELS()
    await DICT_SALARY_AREAS()
    paths = [request.url.path for request in mock_hh.requests]
    assert paths == [
        "/salary_statistics/dictionaries/salary_industries",
        "/salary_statistics/dictionaries/professional_areas",
        "/salary_statistics/dictionaries/employee_levels",
        "/salary_statistics/dictionaries/salary_areas",
    ]
    assert all(dict(request.url.params) == {} for request in mock_hh.requests)


# --- справочники работодателя ----------------------------------------------


async def test_list_addresses_query(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_LIST_ADDRESSES(
        employer_id="1455",
        changed_after="2026-07-01T00:00:00+0300",
        manager_id="87654321",
        with_manager=True,
        per_page=100,
        page=2,
    )
    request = mock_hh.requests[-1]
    assert request.url.path == "/employers/1455/addresses"
    assert dict(request.url.params) == {
        "changed_after": "2026-07-01T00:00:00+0300",
        "manager_id": "87654321",
        "with_manager": "true",
        "per_page": "100",
        "page": "2",
    }


async def test_get_address_path_and_query(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "77", "address": "Москва"}
    result = await EMPLOYER_GET_ADDRESS(employer_id="1455", address_id="77", with_manager=True)
    assert result["id"] == "77"
    request = mock_hh.requests[-1]
    assert request.url.path == "/employers/1455/addresses/77"
    assert dict(request.url.params) == {"with_manager": "true"}


async def test_employer_scoped_dictionaries_paths(mock_hh: MockHH) -> None:
    """Пять справочников работодателя: только employer_id в пути, query пуст."""
    mock_hh.json_response = {"items": []}
    await EMPLOYER_LIST_DEPARTMENTS(employer_id="1455")
    await EMPLOYER_LIST_PAYABLE_API_ACTIONS(employer_id="1455")
    await EMPLOYER_LIST_TESTS(employer_id="1455")
    await EMPLOYER_LIST_VACANCY_BRANDED_TEMPLATES(employer_id="1455")
    await EMPLOYER_LIST_ACTIVE_VACANCY_AREAS(employer_id="1455")
    paths = [request.url.path for request in mock_hh.requests]
    assert paths == [
        "/employers/1455/departments",
        "/employers/1455/services/payable_api_actions/active",
        "/employers/1455/tests",
        "/employers/1455/vacancy_branded_templates",
        "/employers/1455/vacancy_areas/active",
    ]
    assert all(dict(request.url.params) == {} for request in mock_hh.requests)


async def test_list_available_publications_query(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"suitable_packages": []}
    await EMPLOYER_LIST_AVAILABLE_PUBLICATIONS(
        employer_id="1455", area_id="1", professional_role_id="6"
    )
    request = mock_hh.requests[-1]
    assert request.url.path == "/employers/1455/services/available_publications"
    assert dict(request.url.params) == {"area_id": "1", "professional_role_id": "6"}


# --- звонки -----------------------------------------------------------------


async def test_call_history_filters_and_repeated_ids(mock_hh: MockHH) -> None:
    """vacancy_id – множественный параметр (повторяется в query)."""
    mock_hh.json_response = {"calls": [], "total": 0}
    await EMPLOYER_GET_CALL_HISTORY(
        vacancy_id=["123", "456"],
        date_from="2026-07-01T00:00:00+00:00",
        date_to="2026-07-31T23:59:59+00:00",
        per_page=100,
        successful=True,
        direction="outgoing",
        with_resume=True,
        without_vacancy=False,
        link_id="0e4f2a90-7f33-4a5a-9e2f-9a1f0e4d5c6b",
        with_records=True,
        with_transcripts=True,
    )
    request = mock_hh.requests[-1]
    assert request.url.path == "/calls/history"
    assert request.url.params.get_list("vacancy_id") == ["123", "456"]
    params = {k: v for k, v in request.url.params.items() if k != "vacancy_id"}
    assert params == {
        "date_from": "2026-07-01T00:00:00+00:00",
        "date_to": "2026-07-31T23:59:59+00:00",
        "per_page": "100",
        "successful": "true",
        "direction": "outgoing",
        "with_resume": "true",
        "without_vacancy": "false",
        "link_id": "0e4f2a90-7f33-4a5a-9e2f-9a1f0e4d5c6b",
        "with_records": "true",
        "with_transcripts": "true",
    }


async def test_call_history_cursor_params(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"calls": [], "total": 0}
    await EMPLOYER_GET_CALL_HISTORY(next_cursor="abc")
    assert dict(mock_hh.requests[-1].url.params) == {"next_cursor": "abc"}


async def test_call_link_required_resume_id(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"link_id": "uuid-1", "expires_at": "2026-07-01T12:00:00Z"}
    result = await EMPLOYER_GET_CALL_LINK(resume_id="9f3f", vacancy_id="777")
    assert result["link_id"] == "uuid-1"
    request = mock_hh.requests[-1]
    assert request.url.path == "/calls/link"
    assert dict(request.url.params) == {"resume_id": "9f3f", "vacancy_id": "777"}


async def test_call_link_resume_id_is_required() -> None:
    signature = EMPLOYER_GET_CALL_LINK.__signature__  # type: ignore[attr-defined]
    param = signature.parameters["resume_id"]
    assert param.default is param.empty


async def test_search_call_records_post_without_confirm(mock_hh: MockHH) -> None:
    """POST-поиск записей: чтение – без confirm, тело уходит в JSON."""
    mock_hh.json_response = {"records": {}}
    result = await EMPLOYER_SEARCH_CALL_RECORDS(body={"call_ids": ["c1", "c2"]})
    assert result == {"records": {}}
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/calls/records/search"
    assert dict(request.url.params) == {}
    assert json.loads(request.read()) == {"call_ids": ["c1", "c2"]}


async def test_search_call_transcripts_post_without_confirm(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"transcripts": {}}
    await EMPLOYER_SEARCH_CALL_TRANSCRIPTS(
        body={"link_ids": ["0e4f2a90-7f33-4a5a-9e2f-9a1f0e4d5c6b"]}
    )
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/calls/transcripts/search"
    assert json.loads(request.read()) == {"link_ids": ["0e4f2a90-7f33-4a5a-9e2f-9a1f0e4d5c6b"]}


def test_post_searches_have_no_confirm_parameter() -> None:
    """POST-поиски не получают служебный параметр confirm."""
    for tool in (EMPLOYER_SEARCH_CALL_RECORDS, EMPLOYER_SEARCH_CALL_TRANSCRIPTS):
        signature = tool.__signature__  # type: ignore[attr-defined]
        assert "confirm" not in signature.parameters


# --- Clickme и webhook-подписки ---------------------------------------------


async def test_clickme_statistics_required_dates(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_GET_CLICKME_STATISTICS(
        date_from="2026-07-01", date_to="2026-07-31", with_banners=True
    )
    request = mock_hh.requests[-1]
    assert request.url.path == "/clickme/statistics"
    assert dict(request.url.params) == {
        "date_from": "2026-07-01",
        "date_to": "2026-07-31",
        "with_banners": "true",
    }


async def test_list_webhook_subscriptions_no_params(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_LIST_WEBHOOK_SUBSCRIPTIONS()
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/webhook/subscriptions"
    assert dict(request.url.params) == {}


async def test_create_webhook_subscription_body(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "1"}
    await EMPLOYER_CREATE_WEBHOOK_SUBSCRIPTION(
        body={"url": "https://example.test/hook", "actions": [{"type": "VACANCY_CHANGE"}]},
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/webhook/subscriptions"
    assert json.loads(request.read()) == {
        "url": "https://example.test/hook",
        "actions": [{"type": "VACANCY_CHANGE"}],
    }


async def test_update_webhook_subscription_path_and_body(mock_hh: MockHH) -> None:
    mock_hh.json_response = None
    await EMPLOYER_UPDATE_WEBHOOK_SUBSCRIPTION(
        subscription_id="5",
        body={"actions": [{"type": "CHAT_MESSAGE_CREATED"}]},
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/webhook/subscriptions/5"
    assert json.loads(request.read()) == {"actions": [{"type": "CHAT_MESSAGE_CREATED"}]}


async def test_delete_webhook_subscription(mock_hh: MockHH) -> None:
    mock_hh.json_response = None
    await EMPLOYER_DELETE_WEBHOOK_SUBSCRIPTION(subscription_id="5", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "DELETE"
    assert request.url.path == "/webhook/subscriptions/5"


# --- зарплатная статистика и шаблоны сообщений ------------------------------


async def test_salary_evaluation_path_and_query(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"salary": {"value": 150000}}
    await EMPLOYER_GET_SALARY_EVALUATION(
        area_id="1",
        exclude_area="2",
        employee_level="senior",
        industry="7",
        speciality="12",
        extend_sources=True,
        position_name="Разработчик",
    )
    request = mock_hh.requests[-1]
    assert request.url.path == "/salary_statistics/paid/salary_evaluation/1"
    assert dict(request.url.params) == {
        "exclude_area": "2",
        "employee_level": "senior",
        "industry": "7",
        "speciality": "12",
        "extend_sources": "true",
        "position_name": "Разработчик",
    }


async def test_get_message_template_topic(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"messages": []}
    await GET_MESSAGE_TEMPLATE(template="invite", topic_id="424242")
    request = mock_hh.requests[-1]
    assert request.url.path == "/message_templates/invite"
    assert dict(request.url.params) == {"topic_id": "424242"}


async def test_get_message_template_vacancy_resume_pair(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"messages": []}
    await GET_MESSAGE_TEMPLATE(template="invite_after_response", vacancy_id="777", resume_id="9f3f")
    assert dict(mock_hh.requests[-1].url.params) == {
        "vacancy_id": "777",
        "resume_id": "9f3f",
    }


# --- confirm и реестр -------------------------------------------------------


_MUTATION_MINIMAL_ARGS: dict[str, dict[str, Any]] = {
    "employer_create_webhook_subscription": {
        "body": {"url": "https://example.test/hook", "actions": [{"type": "VACANCY_CHANGE"}]}
    },
    "employer_update_webhook_subscription": {
        "subscription_id": "5",
        "body": {"url": "https://example.test/hook2"},
    },
    "employer_delete_webhook_subscription": {"subscription_id": "5"},
}

_MUTATION_TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "employer_create_webhook_subscription": EMPLOYER_CREATE_WEBHOOK_SUBSCRIPTION,
    "employer_update_webhook_subscription": EMPLOYER_UPDATE_WEBHOOK_SUBSCRIPTION,
    "employer_delete_webhook_subscription": EMPLOYER_DELETE_WEBHOOK_SUBSCRIPTION,
}


@pytest.mark.parametrize("tool_name", sorted(MUTATIONS))
async def test_mutations_require_confirm(tool_name: str, mock_hh: MockHH) -> None:
    """Без confirm=True – структурированная ошибка, HTTP не выполняется."""
    tool = _MUTATION_TOOLS[tool_name]
    with pytest.raises(HHError) as excinfo:
        await tool(**_MUTATION_MINIMAL_ARGS[tool_name])
    assert excinfo.value.code == "confirm_required"
    assert "confirm=True" in excinfo.value.description
    assert mock_hh.requests == []


def test_registry_entries_and_flags() -> None:
    entries = REGISTRY.by_toolset("employer_misc")
    assert len(entries) == 25
    for entry in entries:
        assert entry.requires_auth is (entry.name not in PUBLIC_TOOLS), entry.name
        assert entry.is_mutation is (entry.name in MUTATIONS), entry.name


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "GET /employers",
        "GET /employers/{employer_id}",
        "GET /employers/{employer_id}/addresses",
        "GET /employers/{employer_id}/addresses/{address_id}",
        "GET /employers/{employer_id}/departments",
        "GET /employers/{employer_id}/services/payable_api_actions/active",
        "GET /employers/{employer_id}/services/available_publications",
        "GET /employers/{employer_id}/tests",
        "GET /employers/{employer_id}/vacancy_branded_templates",
        "GET /employers/{employer_id}/vacancy_areas/active",
        "GET /calls/history",
        "GET /calls/link",
        "POST /calls/records/search",
        "POST /calls/transcripts/search",
        "GET /clickme/statistics",
        "GET /webhook/subscriptions",
        "POST /webhook/subscriptions",
        "PUT /webhook/subscriptions/{subscription_id}",
        "DELETE /webhook/subscriptions/{subscription_id}",
        "GET /salary_statistics/dictionaries/salary_industries",
        "GET /salary_statistics/dictionaries/professional_areas",
        "GET /salary_statistics/dictionaries/employee_levels",
        "GET /salary_statistics/dictionaries/salary_areas",
        "GET /salary_statistics/paid/salary_evaluation/{area_id}",
        "GET /message_templates/{template}",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None
