"""Тесты набора инструментов «employer_resumes» против MockTransport."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs

import pytest
from fastmcp import Client, FastMCP

from ati_hh_mcp import toolkit
from ati_hh_mcp.hh.client import HHClient
from ati_hh_mcp.hh.errors import HHError
from ati_hh_mcp.registry import REGISTRY
from ati_hh_mcp.toolsets import employer_resumes
from ati_hh_mcp.toolsets.employer_resumes import (
    EMPLOYER_ADD_APPLICANT_COMMENT,
    EMPLOYER_ASSIGN_SAVED_SEARCH_MANAGER,
    EMPLOYER_CREATE_SAVED_SEARCH,
    EMPLOYER_DELETE_APPLICANT_COMMENT,
    EMPLOYER_DELETE_SAVED_SEARCH,
    EMPLOYER_GET_SAVED_SEARCH,
    EMPLOYER_LIST_APPLICANT_COMMENTS,
    EMPLOYER_LIST_SAVED_SEARCHES,
    EMPLOYER_SEARCH_RESUMES,
    EMPLOYER_UPDATE_APPLICANT_COMMENT,
    EMPLOYER_UPDATE_SAVED_SEARCH,
    ResumeSearchAdvanced,
)

from ..conftest import MockHH, make_config

READ_TOOLS = frozenset(
    {
        "employer_search_resumes",
        "employer_list_saved_searches",
        "employer_get_saved_search",
        "employer_list_applicant_comments",
    }
)

MUTATIONS = frozenset(
    {
        "employer_create_saved_search",
        "employer_update_saved_search",
        "employer_delete_saved_search",
        "employer_assign_saved_search_manager",
        "employer_add_applicant_comment",
        "employer_update_applicant_comment",
        "employer_delete_applicant_comment",
    }
)

# 49 неслужебных query-параметров GET /resumes по вендорённой спеке
# (Host/Locale/HHUserAgent задаёт клиент). Имена с точкой переносятся
# во вложенную модель как псевдонимы.
RESUME_SEARCH_SPEC_PARAMS = frozenset(
    {
        "text",
        "text.logic",
        "text.field",
        "text.period",
        "text.company_size",
        "age_from",
        "age_to",
        "area",
        "relocation",
        "period",
        "date_from",
        "date_to",
        "education_level",
        "employment_form",
        "experience",
        "skill",
        "gender",
        "label",
        "language",
        "metro",
        "currency",
        "salary_from",
        "salary_to",
        "work_format",
        "order_by",
        "citizenship",
        "work_ticket",
        "educational_institution",
        "search_in_responses",
        "by_text_prefix",
        "driver_license_types",
        "vacancy_id",
        "page",
        "per_page",
        "professional_role",
        "folder",
        "include_all_folders",
        "job_search_status",
        "resume",
        "filter_exp_industry",
        "filter_exp_period",
        "with_job_search_status",
        "education_levels",
        "district",
        "saved_search_id",
        "search_by_vacancy_id",
        "last_used_timestamp",
        "last_used",
        "business_trip_readiness",
    }
)


@pytest.fixture(autouse=True)
def bound_client(mock_hh: MockHH) -> None:
    """Каждый тест набора работает против подставленного транспорта."""
    toolkit.set_client_factory(lambda: HHClient(make_config(), transport=mock_hh.transport))


# --- employer_search_resumes: двухуровневая схема -------------------------


async def test_search_resumes_frequent_params(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": [], "found": 3, "page": 0, "pages": 1}
    result = await EMPLOYER_SEARCH_RESUMES(
        text="python developer",
        area="1,2",
        salary_from=150000.0,
        salary_to=300000.0,
        currency="RUR",
        experience="between3And6",
        employment_form="full",
        label="only_with_salary",
        order_by="relevance",
        page=1,
        per_page=50,
    )
    assert result["found"] == 3
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/resumes"
    assert dict(request.url.params) == {
        "text": "python developer",
        "area": "1,2",
        "salary_from": "150000.0",
        "salary_to": "300000.0",
        "currency": "RUR",
        "experience": "between3And6",
        "employment_form": "full",
        "label": "only_with_salary",
        "order_by": "relevance",
        "page": "1",
        "per_page": "50",
    }


async def test_search_resumes_advanced_only_set_fields(mock_hh: MockHH) -> None:
    """Вложенная advanced-модель: в запрос попадают только заданные поля."""
    mock_hh.json_response = {"items": []}
    await EMPLOYER_SEARCH_RESUMES(
        text="инженер",
        advanced=ResumeSearchAdvanced(
            **{
                "text.logic": "all",
                "text.field": "experience,keywords",
                "relocation": "none",
                "folder": "111",
            },
        ),
    )
    params = dict(mock_hh.requests[-1].url.params)
    assert params == {
        "text": "инженер",
        "text.logic": "all",
        "text.field": "experience,keywords",
        "relocation": "none",
        "folder": "111",
    }
    # Незаданные поля хвоста не попадают в запрос.
    assert "by_text_prefix" not in params
    assert "saved_search_id" not in params


async def test_search_resumes_advanced_alias_serialization(
    mock_hh: MockHH,
) -> None:
    """Поля-псевдонимы сериализуются под именами из спеки (text.logic)."""
    mock_hh.json_response = {"items": []}
    advanced = ResumeSearchAdvanced(text_logic="all", text_period="")
    assert advanced.model_dump(exclude_none=True) == {
        "text.logic": "all",
        "text.period": "",
    }
    await EMPLOYER_SEARCH_RESUMES(advanced=advanced)
    assert dict(mock_hh.requests[-1].url.params) == {
        "text.logic": "all",
        "text.period": "",
    }


async def test_search_resumes_no_unnecessary_query(mock_hh: MockHH) -> None:
    """Вызов без параметров: query полностью пуст (None не отправляется)."""
    await EMPLOYER_SEARCH_RESUMES()
    assert dict(mock_hh.requests[-1].url.params) == {}


def test_search_resumes_all_spec_params_available() -> None:
    """Все 49 параметров спеки доступны: верхний уровень + advanced-хвост."""
    top_level = set(employer_resumes.ResumeSearchParams.model_fields) - {"advanced"}
    advanced_names = set(ResumeSearchAdvanced.model_json_schema()["properties"])
    assert (top_level | advanced_names) == set(RESUME_SEARCH_SPEC_PARAMS)
    # Имена с точкой приходят в схему именно из advanced-модели.
    assert {"text.logic", "text.field", "text.period", "text.company_size"} <= advanced_names


async def test_search_resumes_via_mcp_layer_dotted_params(
    mock_hh: MockHH,
) -> None:
    """Через реальный MCP-клиент advanced приходит объектом с точечными
    ключами из спеки и разворачивается в query без потерь."""
    mock_hh.json_response = {"items": []}
    server = FastMCP(name="test-employer-resumes")
    employer_resumes.register(
        server,
        client_factory=lambda: HHClient(make_config(), transport=mock_hh.transport),
    )
    async with Client(server) as client:
        await client.call_tool(
            "employer_search_resumes",
            {"text": "go", "advanced": {"text.logic": "all", "language": "eng.c2"}},
        )
    request = mock_hh.requests[-1]
    assert request.url.path == "/resumes"
    assert dict(request.url.params) == {
        "text": "go",
        "text.logic": "all",
        "language": "eng.c2",
    }


# --- сохранённые поиски ----------------------------------------------------


async def test_list_saved_searches_pagination(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_LIST_SAVED_SEARCHES(page=0, per_page=10)
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/saved_searches/resumes"
    assert dict(request.url.params) == {"page": "0", "per_page": "10"}


async def test_create_saved_search_all_params_in_query(
    mock_hh: MockHH,
) -> None:
    """POST автопоиска: все заданные параметры уходят в query, тело пусто."""
    mock_hh.json_response = None
    await EMPLOYER_CREATE_SAVED_SEARCH(
        text="python",
        area="1",
        salary_from=100000.0,
        currency="RUR",
        experience="between1And3",
        employment_form="full",
        order_by="relevance",
        page=0,
        per_page=10,
        search_in_responses=True,
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/saved_searches/resumes"
    assert dict(request.url.params) == {
        "text": "python",
        "area": "1",
        "salary_from": "100000.0",
        "currency": "RUR",
        "experience": "between1And3",
        "employment_form": "full",
        "order_by": "relevance",
        "page": "0",
        "per_page": "10",
        "search_in_responses": "true",
    }
    assert request.read() == b""  # JSON-тело не отправляется.


def test_create_saved_search_model_has_no_body_field() -> None:
    """query_fields объявления покрывают все поля модели – в тело ничего не уходит."""
    fields = set(employer_resumes.SavedSearchCreateParams.model_fields)
    assert "body" not in fields
    assert "advanced" not in fields
    assert len(fields) == 29  # 32 параметра спеки минус триада text.* с точками.


# --- автопоиски: единичный, обновление, удаление, передача -----------------


async def test_get_saved_search_path_substitution(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"id": "123", "query": "~python"}
    result = await EMPLOYER_GET_SAVED_SEARCH(id="123")
    assert result["id"] == "123"
    request = mock_hh.requests[-1]
    assert request.url.path == "/saved_searches/resumes/123"
    assert dict(request.url.params) == {}


async def test_update_saved_search_query_params_only(
    mock_hh: MockHH,
) -> None:
    """PUT автопоиска: name/subscription в query, JSON-тела нет."""
    mock_hh.json_response = None
    await EMPLOYER_UPDATE_SAVED_SEARCH(id="42", name="Senior Go", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/saved_searches/resumes/42"
    assert dict(request.url.params) == {"name": "Senior Go"}
    assert request.read() == b""


async def test_update_saved_search_unsubscription_false_sent(
    mock_hh: MockHH,
) -> None:
    """subscription=False – осмысленное значение, попадает в query."""
    mock_hh.json_response = None
    await EMPLOYER_UPDATE_SAVED_SEARCH(id="42", subscription=False, confirm=True)
    assert dict(mock_hh.requests[-1].url.params) == {"subscription": "false"}


async def test_delete_saved_search(mock_hh: MockHH) -> None:
    mock_hh.json_response = None
    await EMPLOYER_DELETE_SAVED_SEARCH(id="42", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "DELETE"
    assert request.url.path == "/saved_searches/resumes/42"


async def test_assign_saved_search_manager_two_path_params(
    mock_hh: MockHH,
) -> None:
    mock_hh.json_response = None
    await EMPLOYER_ASSIGN_SAVED_SEARCH_MANAGER(saved_search_id="42", manager_id="77", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/saved_searches/resumes/42/managers/77"
    assert dict(request.url.params) == {}


async def test_list_applicant_comments(mock_hh: MockHH) -> None:
    mock_hh.json_response = {"items": []}
    await EMPLOYER_LIST_APPLICANT_COMMENTS(
        applicant_id="54761929", page=0, per_page=30, order_by="creation_time"
    )
    request = mock_hh.requests[-1]
    assert request.method == "GET"
    assert request.url.path == "/applicant_comments/54761929"
    assert dict(request.url.params) == {
        "page": "0",
        "per_page": "30",
        "order_by": "creation_time",
    }


async def test_add_applicant_comment_form_body(mock_hh: MockHH) -> None:
    """Спека декларирует x-www-form-urlencoded – тело уходит form-encoded."""
    mock_hh.json_response = {"id": "9", "text": "Strong candidate"}
    await EMPLOYER_ADD_APPLICANT_COMMENT(
        applicant_id="54761929",
        body={"text": "Strong candidate", "access_type": "company"},
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/applicant_comments/54761929"
    assert dict(request.url.params) == {}
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.read().decode()) == {
        "text": ["Strong candidate"],
        "access_type": ["company"],
    }


async def test_update_applicant_comment_form_body(mock_hh: MockHH) -> None:
    mock_hh.json_response = None
    await EMPLOYER_UPDATE_APPLICANT_COMMENT(
        applicant_id="54761929",
        comment_id="9",
        body={"access_type": "manager"},
        confirm=True,
    )
    request = mock_hh.requests[-1]
    assert request.method == "PUT"
    assert request.url.path == "/applicant_comments/54761929/9"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.read().decode()) == {"access_type": ["manager"]}


async def test_delete_applicant_comment(mock_hh: MockHH) -> None:
    mock_hh.json_response = None
    await EMPLOYER_DELETE_APPLICANT_COMMENT(applicant_id="54761929", comment_id="9", confirm=True)
    request = mock_hh.requests[-1]
    assert request.method == "DELETE"
    assert request.url.path == "/applicant_comments/54761929/9"


# --- confirm и реестр -------------------------------------------------------


_MUTATION_MINIMAL_ARGS: dict[str, dict[str, Any]] = {
    "employer_create_saved_search": {},
    "employer_update_saved_search": {"id": "42"},
    "employer_delete_saved_search": {"id": "42"},
    "employer_assign_saved_search_manager": {"saved_search_id": "42", "manager_id": "77"},
    "employer_add_applicant_comment": {
        "applicant_id": "1",
        "body": {"text": "x", "access_type": "company"},
    },
    "employer_update_applicant_comment": {
        "applicant_id": "1",
        "comment_id": "2",
        "body": {"text": "x"},
    },
    "employer_delete_applicant_comment": {"applicant_id": "1", "comment_id": "2"},
}

_MUTATION_TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "employer_create_saved_search": EMPLOYER_CREATE_SAVED_SEARCH,
    "employer_update_saved_search": EMPLOYER_UPDATE_SAVED_SEARCH,
    "employer_delete_saved_search": EMPLOYER_DELETE_SAVED_SEARCH,
    "employer_assign_saved_search_manager": EMPLOYER_ASSIGN_SAVED_SEARCH_MANAGER,
    "employer_add_applicant_comment": EMPLOYER_ADD_APPLICANT_COMMENT,
    "employer_update_applicant_comment": EMPLOYER_UPDATE_APPLICANT_COMMENT,
    "employer_delete_applicant_comment": EMPLOYER_DELETE_APPLICANT_COMMENT,
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
    entries = REGISTRY.by_toolset("employer_resumes")
    assert len(entries) == 11
    assert sorted(e.name for e in entries) == sorted(MUTATIONS | READ_TOOLS)
    for entry in entries:
        assert entry.requires_auth is True, entry.name
        assert entry.is_mutation is (entry.name in MUTATIONS), entry.name


def test_registry_lookup_by_operation() -> None:
    for operation_id in (
        "GET /resumes",
        "GET /saved_searches/resumes",
        "POST /saved_searches/resumes",
        "GET /saved_searches/resumes/{id}",
        "PUT /saved_searches/resumes/{id}",
        "DELETE /saved_searches/resumes/{id}",
        "PUT /saved_searches/resumes/{saved_search_id}/managers/{manager_id}",
        "GET /applicant_comments/{applicant_id}",
        "POST /applicant_comments/{applicant_id}",
        "PUT /applicant_comments/{applicant_id}/{comment_id}",
        "DELETE /applicant_comments/{applicant_id}/{comment_id}",
    ):
        assert REGISTRY.get_by_operation(operation_id) is not None
